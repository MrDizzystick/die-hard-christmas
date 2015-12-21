jQuery(function( $ ) {
    console.log("Device ID cookie: " + getCookie("device_id"));

    // Keep track of failures when trying to contact server.
    // This way we can hide certain UI elements to prevent the user from trying to trigger things.
    server_connection_failures = 0;

    // Set up charts.
    chart_drinks_over_time_data = {labels: ['Start'], series: [ [0] ]};
    chart_drinks_over_time_options = {
        chartPadding: { left: 10, bottom: -10, top: 5 },
        low: 0,
        showArea: true,
        axisX: {
            showLabel: false
        },
        axisY: {
            showGrid: false,
            showLabel: false
        }
    };
    chart_drinks_over_time = new Chartist.Line('#mini-drink-chart', chart_drinks_over_time_data, chart_drinks_over_time_options);


    chart_drinks_submitted_by_user_data = {labels: ['Nobody'], series: [0]};
    chart_drinks_submitted_by_user_options = {
        horizontalBars: true,
        distributeSeries: true,
        axisX: {onlyInteger: true}
    };
    chart_drinks_submitted_by_user = new Chartist.Bar('#chart-drinks-submitted-by-user', chart_drinks_submitted_by_user_data, chart_drinks_submitted_by_user_options);


    chart_drinks_by_type_data = {labels: ['N/A'], series: [1]};
    chart_drinks_by_type_options = {
        //chartPadding: 15,
        //labelOffset: 50,
        //labelDirection: 'explode'

        //showLabel: false
        horizontalBars: true,
        distributeSeries: true,
        //axisY: {showLabel: false},
        axisX: {onlyInteger: true}
    };
    chart_drinks_by_type = new Chartist.Bar('#chart-drinks-by-type', chart_drinks_by_type_data, chart_drinks_by_type_options);


    chart_drinks_by_location_data = {labels: ['N/A'], series: [0]};
    chart_drinks_by_location_options = {
        horizontalBars: true,
        distributeSeries: true,
        axisX: {onlyInteger: true}
    };
    chart_drinks_by_location = new Chartist.Bar('#chart-drinks-by-location', chart_drinks_by_location_data, chart_drinks_by_location_options);

    chart_number_of_piss_breaks_by_user_data = {labels: ['N/A'], series: [0]};
    chart_number_of_piss_breaks_by_user_options = {
        horizontalBars: true,
        distributeSeries: true,
        axisX: {onlyInteger: true}
    };
    chart_number_of_piss_breaks_by_user = new Chartist.Bar('#chart-number-of-piss-breaks-by-user', chart_number_of_piss_breaks_by_user_data, chart_number_of_piss_breaks_by_user_options);

    // $("#toggle_fullscreen").click(function() {
    //     toggleFullscreen(document.documentElement);
    // });

    //////////////////
    // User buttons
    //////////////////

    // Assign the "That's a Drink" button a special timer action on click.
    // Disables the button temporarily, sends a drink request, then re-enables button after a delay.
    $('#thats-a-drink-button').click(function() {
        // Temporarily disable button.
        var drink_delay_seconds = 5;
        var btn = $(this);
        btn.prop('disabled', true);
        btn.removeClass('btn-primary');
        btn.addClass('btn-danger');
        action_request('drink');  // Send drink request to server.
        setTimeout(function() {
            // Re-enable after a moment.
            btn.removeClass('btn-danger');
            btn.addClass('btn-primary');
            btn.prop('disabled', false);
        }, drink_delay_seconds * 1000);
    });

    // Piss Break Button
    $("#piss-break-button").click(function() {
        $("#piss-break-button").prop('disabled', true);  // TODO: Is this actually disabling the button...? Is it needed?
        action_request('piss_break');
    });

    $("#piss-break-finished").click(function() {
        action_request('piss_break');
    });

    // Update BRAC Button
    $("#update-brac-button").click(function() {
        $("#update-brac-modal").modal();
    });

    $("#submit-brac-button").click(function() {
        // Send the data to the server to log it.
        action_request('brac_update' + $('#brac_value').val());
    });

    // Set "Next Drink" to be toggleable by tapping on the header.
    $("#next-drink-display-toggle").click(function() {
        $("#next-drink-value").toggle();
    });

    // Fake question button actions.
    $(".fake-question-button").click(function() {
        action_request('drink');
    });

    // Navigation menu buttons.
    $("#show_home_page, #dhc-title").click(function() {
        $("#view-admin").hide();
        $("#view-stats").hide();
        $("#view-nakatomi-map").hide();
        $("#view-main").fadeIn("fast");
        $("#show_home_page").parent().parent().hide();
        $("#show_stats_page").parent().parent().show();
        $("#show_map_page").parent().parent().show();
        $("#show_admin_page").parent().parent().show();
    });

    $("#show_stats_page").click(function() {
        $("#view-main").hide();
        $("#view-admin").hide();
        $("#view-nakatomi-map").hide();
        $("#view-stats").fadeIn("fast");
        $("#show_home_page").parent().parent().show();
        $("#show_stats_page").parent().parent().hide();
        $("#show_map_page").parent().parent().show();
        $("#show_admin_page").parent().parent().show();
    });

    $("#show_map_page").click(function() {
        $("#view-main").hide();
        $("#view-stats").hide();
        $("#view-admin").hide();
        $("#view-nakatomi-map").fadeIn("fast");
        $("#show_home_page").parent().parent().show();
        $("#show_stats_page").parent().parent().show();
        $("#show_map_page").parent().parent().hide();
        $("#show_admin_page").parent().parent().show();
    });

    $("#show_admin_page").click(function() {
        $("#view-main").hide();
        $("#view-stats").hide();
        $("#view-nakatomi-map").hide();
        $("#view-admin").fadeIn("fast");
        $("#show_home_page").parent().parent().show();
        $("#show_stats_page").parent().parent().show();
        $("#show_map_page").parent().parent().show();
        $("#show_admin_page").parent().parent().hide();
    });

    //////////////////
    // Admin buttons
    //////////////////

    $("#admin-playback-start").click(function() {
        if (confirm("Start/restart the movie?")) {
            action_request('admin_playback_start');
        }
    });

    $("#admin-playback-pause").click(function() {
        action_request('admin_playback_pause');
    });

    $("#fun_snow").click(function() {
        action_request('fun_snow');
    });

    $("#fun_skill_test").click(function() {
        action_request('fun_skill_test');
    });

    $("#fun_brac_logging").click(function() {
        action_request('fun_brac_logging');
    });

    $("#fun_led_lighting").click(function() {
        action_request('fun_led_lighting');
    });

    //////////////////
    // The rest of the coding junk.
    //////////////////

    // Get user's name into proper fields.
    action_request('username');

    map_image_list = [
        "/img/map/482.png",
        "/img/map/545.png",
        "/img/map/638.png",
        "/img/map/648.png",
        "/img/map/656.png",
        "/img/map/1035.png",
        "/img/map/1050.png",
        "/img/map/1153.png",
        "/img/map/1438.png",
        "/img/map/1463.png",
        "/img/map/1601.png",
        "/img/map/1642.png",
        "/img/map/1707.png",
        "/img/map/2045.png",
        "/img/map/2069.png",
        "/img/map/2120.png",
        "/img/map/2254.png",
        "/img/map/2423.png",
        "/img/map/2523.png",
        "/img/map/2613.png",
        "/img/map/2882.png",
        "/img/map/3077.png",
        "/img/map/3340.png",
        "/img/map/3380.png",
        "/img/map/3752.png",
        "/img/map/4380.png",
        "/img/map/4496.png",
        "/img/map/4500.png",
        "/img/map/4539.png",
        "/img/map/4601.png",
        "/img/map/5407.png",
        "/img/map/5535.png",
        "/img/map/5561.png",
        "/img/map/5747.png",
        "/img/map/5768.png",
        "/img/map/6491.png",
        "/img/map/6816.png",
        "/img/map/6826.png",
        "/img/map/6990.png",
        "/img/map/7015.png",
        "/img/map/7106.png",
        "/img/map/7181.png",
        "/img/map/7191.png",
        "/img/map/7321.png",
        "/img/map/7377.png",
        "/img/map/7393.png",
        "/img/map/7542.png"
    ];

    // Preload images for Nakatomi Plaza Map.
    function preload_images () {
        for (var i = 0; i < map_image_list.length; i++) {
            var image_object = new Image();
            image_object.src = map_image_list[i];
        }
    }

    // Preload map images.
    preload_images();

    // Start looping functions.
    checkServer();

    // Function to automatically request drink info from server:
    function checkServer () {
        $.ajax({
            url: '/get_data',
            type: 'POST',
            dataType: 'json',
            success: function(data) {
                // Reset failure count to 0, hide connection failure alert.
                server_connection_failures = 0;
                $("#alert-no-server").hide();

                // Update elements with received data.
                recent_drink_list_data = "";
                data.recent_list.forEach(function(obj) {
                    recent_drink_list_data = recent_drink_list_data + "<td style='white-space: nowrap; width: 1px;'>" + obj.executed_at + "</td><td>" + obj.event_reason + "</td></tr>";
                });
                $('#recent-drink-list').html('<table class="table table-striped table-condensed small">' + recent_drink_list_data + '</table>');
                $('#drink-total-value').html(data.total_drinks);
                $('#next-drink-value').html((data.next_drink - data.playback_time) + "<span style=\"font-size: 0.75em;\"> sec.</span>");
                $('#drink-rate-value').html(data.drinks_per_minute);

                // Update chart data.
                chart_drinks_over_time.data = data.drinks_over_time;
                chart_drinks_over_time.update();

                var chart_height_min = 40;
                var chart_height_step = 20;
                chart_drinks_submitted_by_user.data = data.chart_drinks_submitted_by_user;
                $('#chart-drinks-submitted-by-user').height(chart_height_min + (chart_height_step * data.chart_drinks_submitted_by_user.labels.length) );
                chart_drinks_submitted_by_user.update();
                chart_drinks_by_type.data = data.chart_drinks_by_type;
                $('#chart-drinks-by-type').height(chart_height_min + (chart_height_step * data.chart_drinks_by_type.labels.length) );
                chart_drinks_by_type.update();
                chart_drinks_by_location.data = data.chart_drinks_by_location;
                $('#chart-drinks-by-location').height(chart_height_min + (chart_height_step * data.chart_drinks_by_location.labels.length) );
                chart_drinks_by_location.update();
                chart_number_of_piss_breaks_by_user.data = data.chart_number_of_piss_breaks_by_user;
                $('#chart-number-of-piss-breaks-by-user').height(chart_height_min + (chart_height_step * data.chart_number_of_piss_breaks_by_user.labels.length) );
                chart_number_of_piss_breaks_by_user.update();

                if (data.playback_is_playing == true) {
                    // During playback, hide migle message, show the rest of the UI.
                    $("#thank-user-mingle").fadeOut("fast");
                    //$("#mini-drink-chart").css("visibility", "visible");  // Visibility to workaround chart not using correct size if "display: none".
                    $("#mini-drink-chart-div").fadeIn("fast");
                    $("#drink-total-next").fadeIn("fast");
                    $("#recent-drinks").fadeIn("fast");
                    // $("#drink-piss-buttons").fadeIn("fast");

                    // Get user's piss break status to forcefully show/hide modal if needed.
                    if (data.piss_break_status == true) {
                        $("#drink-piss-buttons").fadeOut("fast");
                        $("#piss-break-modal").modal("show");
                    } else {
                        $("#piss-break-modal").modal("hide");
                        $("#drink-piss-buttons").fadeIn("fast");
                    }

                } else {
                    // Movie is stopped, show mingle message, hide the rest of the UI.
                    $("#thank-user-mingle").fadeIn("fast");
                    $("#mini-drink-chart-div").fadeOut("fast");
                    $("#drink-total-next").fadeOut("fast");
                    $("#recent-drinks").fadeOut("fast");
                    $("#drink-piss-buttons").fadeOut("fast");
                }

                if (data.fun_snow == true) {
                    // Enable snow effect.
                    if (!document.contains(document.getElementById("websnowjqcansnow-canvas"))) {
                        $("#snow-canvas").websnowjq({snowFlakes: 10});
                    }
                } else {
                    // Disable snow effect.
                    if (document.contains(document.getElementById("websnowjqcansnow-canvas"))) {
                        var c = document.getElementById('websnowjqcansnow-canvas');
                        c.parentNode.removeChild(c);
                    }
                }

                if (data.fun_brac_logging == true) {
                    // Enable BRAC button.
                    $("#piss-break-button-div").removeClass("col-xs-6");
                    $("#piss-break-button-div").addClass("col-xs-4");
                    $("#thats-a-drink-button-div").removeClass("col-xs-6");
                    $("#thats-a-drink-button-div").addClass("col-xs-4");
                    $("#update-brac-button-div").fadeIn("fast");
                } else {
                    // Disable BRAC button.
                    $("#update-brac-button-div").hide();
                    $("#piss-break-button-div").removeClass("col-xs-4");
                    $("#piss-break-button-div").addClass("col-xs-6");
                    $("#thats-a-drink-button-div").removeClass("col-xs-4");
                    $("#thats-a-drink-button-div").addClass("col-xs-6");
                }

                // Update Nakatomi Map based on playback time.
                var found_image = false;
                for (var i = 0; i < map_image_list.length; i++) {
                    var str = map_image_list[i]
                    var filename_time = str.substring(str.lastIndexOf("/")+1, str.lastIndexOf("."));
                    if (data.playback_time > Number(filename_time)) {
                        // set map image to this one
                        $('#nakatomi-map').css("background-image", "url(/img/map/" + filename_time + ".png)");
                        found_image = true;
                    }
                };
                if (!found_image) { $('#nakatomi-map').css("background-image", "url(/img/map/default.png)"); }

                // Update admin button colours.
                if (data.fun_snow == true) { $("#fun_snow").removeClass("btn-info").addClass("btn-success").removeClass("btn-danger"); } else { $("#fun_snow").removeClass("btn-info").addClass("btn-danger").removeClass("btn-success"); }
                if (data.fun_skill_test == true) { $("#fun_skill_test").removeClass("btn-info").addClass("btn-success").removeClass("btn-danger"); } else { $("#fun_skill_test").removeClass("btn-info").addClass("btn-danger").removeClass("btn-success"); }
                if (data.fun_brac_logging == true) { $("#fun_brac_logging").removeClass("btn-info").addClass("btn-success").removeClass("btn-danger"); } else { $("#fun_brac_logging").removeClass("btn-info").addClass("btn-danger").removeClass("btn-success"); }
                if (data.fun_led_lighting == true) { $("#fun_led_lighting").removeClass("btn-info").addClass("btn-success").removeClass("btn-danger"); } else { $("#fun_led_lighting").removeClass("btn-info").addClass("btn-danger").removeClass("btn-success"); }
            },
            complete: function() {
                // Schedule the next request when the current one is complete.
                setTimeout(checkServer, 1000); // 1000 = 1 second
            },
            error: function (xhr, ajaxOptions, thrownError) {
                // Increment failure count. If count goes above threshold, activate alert and hide buttons.
                server_connection_failures += 1;
                if (server_connection_failures >= 2) {
                    console.log("Reached failure threshold!");
                    // Hide buttons, show alert.
                    $("#drink-piss-buttons").hide();
                    $("#alert-no-server").show("fast");
                    // Close any open modals (e.g. skill question).
                    $("#skill-test-modal").modal("hide");
                }
            }
        });
    }

    // Used to submit drink requests to server.
    // TODO: Check if Skill-Testing Question is enabled, and show/use modal.
    function action_request (action_request) {
        $.ajax({
            url: '/action',
            type: 'POST',
            dataType: 'json',
            data: { action_request: action_request },
            success: function (response) {
                if (!response.ok && response.reason == 'spam') {
                    // User was spamming the drink button.
                    $("#slow-down-modal").modal()
                } else if (response.ok && !(response.debt == null)) {
                    // User came off of piss break, receive drink debt count.
                    if (response.debt == 1) { $("#piss-break-debt-count").html("1 drink"); }
                    else { $("#piss-break-debt-count").html(response.debt + " drinks"); }
                    $("#piss-break-modal").modal("hide");
                    $("#piss-break-debt-modal").modal("show");
                    $("#piss-break-button").prop('disabled', false);
                } else if (response.ok && !(response.username == null)) {
                    // Update username in the HTML.
                    console.log("Server says username is: " + response.username);
                    $(".username-here").html(response.username);
                }
            }
        });
    }

    // Full screen toggle function.
    function toggleFullscreen(elem) {
        elem = elem || document.documentElement;
        if (!document.fullscreenElement && !document.mozFullScreenElement &&
            !document.webkitFullscreenElement && !document.msFullscreenElement) {
            if (elem.requestFullscreen) {
                elem.requestFullscreen();
            } else if (elem.msRequestFullscreen) {
                elem.msRequestFullscreen();
            } else if (elem.mozRequestFullScreen) {
                elem.mozRequestFullScreen();
            } else if (elem.webkitRequestFullscreen) {
                elem.webkitRequestFullscreen(Element.ALLOW_KEYBOARD_INPUT);
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            }
        }
    }
});