# coding=utf-8
import datetime
import math
import os
import sqlite3
import sys
import uuid
import shutil
import socket
import xbmc
import xbmcaddon
import xbmcgui

# NECESSARY FEATURES
# x Add drink total to web interface.
# x Disable drink request button for 5 seconds after request sent, or if movie paused.
# x Create flashing red/green border effect on each drink event by sliding four rectangles in from the sides of the screen.
# x Add following events: every time mongolian on screen, every explosion, check again for missing argyle and selftalking events. Review a mysterious "ellis"?
# x Fix status update bug, where receiving the status information causes websocket error on client (received data too long?).
# x Admin login/authentication to set user as admin.
# x Administration screen/panel to toggle "fun" options. Only accessible by users marked as admins.
# TODO: Administration page for managing users (delete UUIDs, change names)?
# / Final testing on MacBook Air - check performance, and script to forwarding port 80 to local 8000 for ease of use.

# OPTIONAL FEATURES
# x Log drink events + timestamps to database to make charts of drinks over time after the event.
# x NEW FEATURE: Time to next drink (ETA).
# x NEW FEATURE: Count pending/owed drinks from this point - to help with bathroom breaks, etc.
#   x Roll this in with the "Piss Break" feature.
# x NEW FEATURE: Support for LED lighting effects via "hyperion".
# TODO: NEW FEATURE: Breath Alcohol Content logging (user submit from mobile device, prompt for update every 10-15 mins?)
# x Add statistics page (same HTML page, toggle panel/tab element) to show graphs.
#   - Donut chart with percentage of drinks by type.
#   - Donut chart of percentage drinks by creator.
#   - Coloured time-line showing drink type over time (lines at each drink point in time, coloured by category/type)?
#   - BRAC breakdowns (comparisons of total/peak by user? average value over time by user? combined total of all users?)

# Load XBMC add-on properties.
this_addon = xbmcaddon.Addon()
this_addon_name = this_addon.getAddonInfo('name')
this_addon_version = this_addon.getAddonInfo('version')
this_addon_path = xbmc.translatePath(this_addon.getAddonInfo('path')).decode('utf-8')
# this_addon_icon = this_addon.getAddonInfo('icon')

# Import additional modules from add-on directory since they will not be part of the built-in Python modules in Kodi.
sys.path.insert(0, os.path.join(this_addon_path, "resources", "lib"))
import cherrypy
from mako.lookup import TemplateLookup

diehard_is_playing = False  # Whether the Die Hard movie file is playing. Used to hide UI from other playback (e.g. music).

# Fun event defaults:
fun_skill_test = False
fun_snow = False
fun_brac_logging = False
fun_led_lighting = True


def main():
    global diehard_is_playing
    global fun_skill_test
    global fun_snow
    global fun_brac_logging
    global fun_led_lighting

    # Define resource directories.
    imgdir = os.path.join(this_addon_path, "resources", "images")
    webroot = os.path.join(this_addon_path, "resources", "web")
    webapp_template_lookup = TemplateLookup(directories=[os.path.join(webroot, "templates")])

    wifi_name = ""
    # TODO: Add methods to get current WiFi network name for other platforms.
    if sys.platform == 'darwin':
        wifi_name = str(os.popen("networksetup -getairportnetwork en0 | awk -F\": \" '{print $2}'").read()).strip()

    # Start monitor so we can check for abort request.
    xbmc_monitor = xbmc.Monitor()

    def xbmc_log(message):
        """
        Prints an entry in the XBMC log.
        :param message: The log message to print.
        """
        xbmc.log(u"{0} - {1}".format(this_addon_name, message).encode('utf-8'))

    xbmc_log("Hello! Welcome to Die Hard Christmas!")
    xbmc_log("Add-on version: {0}".format(this_addon_version))
    xbmc_log("Python version: {0}".format(sys.version))
    xbmc_log("Web server root: {0}".format(webroot))
    ipaddress = xbmc.getIPAddress()
    xbmc_log("Web server address: {0}".format(ipaddress))
    try:
        hostname = socket.gethostbyaddr(ipaddress)[0]
    except socket.herror:
        hostname = ipaddress
    xbmc_log("Web server NetBIOS name: {0}".format(hostname))
    xbmc_log("Network name: {0}".format(wifi_name))

    database_file = os.path.join(this_addon_path, "resources", "data", "dhc.db")

    xbmc_log("Loading database: {0}".format(database_file))

    if os.path.exists(database_file):
        xbmc_log("Database was found.")
    else:
        # Bomb out if we couldn't find the database because that's a deal breaker.
        xbmc_log("Database was not found!")
        exit(1)

    class DatabaseManager(object):
        # Handles queries and the like with the SQLite database.
        def __init__(self, db_file):
            self.conn = sqlite3.connect(db_file, detect_types=sqlite3.PARSE_DECLTYPES)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute('pragma foreign_keys = on')
            self.conn.commit()
            self.cur = self.conn.cursor()

        def query(self, sql, params=()):
            try:
                self.cur.execute(sql, params)
                self.conn.commit()
            except sqlite3.Error:
                self.conn.rollback()
            return self.cur

        def __del__(self):
            self.conn.close()

    def get_user_by_uuid(device_id):
        db = DatabaseManager(database_file)
        sql = "SELECT id, name FROM users WHERE device_id = ?"
        params = [device_id]
        return db.query(sql, params).fetchall()

    def reset_drink_history():
        # TODO: Create a backup copy of database to preserve previous data before we clear it.
        try:
            shutil.copyfile(database_file, os.path.join(os.path.dirname(os.path.abspath(database_file)),
                                                        "dhc_{0:%Y%m%d-%H%M%S-%f}.db".format(datetime.datetime.now())))
        except IOError:
            xbmc_log("Couldn't write backup copy of existing database.")
            exit(1)

        db = DatabaseManager(database_file)

        xbmc_log("Removing all records in drink_events table where 'created_by' is not 1 (System)...")
        sql = "DELETE FROM drink_events WHERE created_by != 1"
        db.query(sql)

        xbmc_log("Resetting 'executed_at' for all records in drink_events table...")
        sql = "UPDATE drink_events SET executed_at = NULL"
        db.query(sql)

        xbmc_log("Removing all records in users_history...")
        sql = "DELETE FROM users_history"
        db.query(sql)

        xbmc_log("Resetting 'on_piss_break' for all users in users_history...")
        sql = "UPDATE users SET on_piss_break = NULL"
        db.query(sql)

    def get_reason_text(reason_code):
        db = DatabaseManager(database_file)
        sql = "SELECT description_full FROM drink_reasons WHERE id = ?"
        return db.query(sql, (reason_code,)).fetchone()[0]

    def send_hyperion_command(message=None):
        if fun_led_lighting:
            tcp_ip = this_addon.getSetting("dhc_hyperion_address")
            tcp_port = int(this_addon.getSetting("dhc_hyperion_port"))
            # BUFFER_SIZE = 1024

            if message is None:
                message = '{"command":"effect","duration":10000,"effect":{"name":"Die Hard Xmas Drink Event"},"priority":100}'

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)  # Timeout just in case the hyperion server is unavailable.
                # s.setblocking(False)
                s.connect((tcp_ip, tcp_port))
                s.send(message + '\n')
                s.close()
            except Exception as e:
                xbmc_log("*** Exception while trying to send light command to hyperion:")
                xbmc_log(e)

    # def clamp(val, minv, maxv):
    #     # Clamp value between a minimum and maximum.
    #     return minv if val < minv else maxv if val > maxv else val

    class DieHardWebApp(object):

        def set_cookie(self, cookie_name, cookie_value):
            cherrypy.response.cookie[cookie_name] = str(cookie_value)
            cherrypy.response.cookie[cookie_name]['path'] = '/'
            cherrypy.response.cookie[cookie_name]['max-age'] = 604800  # 7 days
            cherrypy.response.cookie[cookie_name]['version'] = 1

        def get_cookie(self, cookie_name):
            try:
                result = cherrypy.request.cookie[cookie_name].value
                if result == "None":
                    result = None
                return result
            except KeyError:
                return None

        def delete_cookie(self, cookie_name):
            cherrypy.response.cookie[cookie_name] = ''
            cherrypy.response.cookie[cookie_name]['expires'] = 0
            cherrypy.response.cookie[cookie_name]['max-age'] = 0

        # @cherrypy.expose
        # def default(self):
        #     sys.exit()

        @cherrypy.expose
        def index(self, user_name=None, admin_pass=None):

            db = DatabaseManager(database_file)
            response = open(os.path.join(webroot, "login.html"))  # Set default response.

            def generate_id():
                device_id = str(uuid.uuid1())
                xbmc_log("Generated device ID: {0}.".format(device_id))

                sql = "INSERT INTO users (device_id) VALUES (?)"
                params = [device_id]
                db.query(sql, params)
                return device_id

            client_device_id = self.get_cookie("device_id")
            xbmc_log(
                    "Got device_id cookie value: {0}, which is type: {1}".format(client_device_id,
                                                                                 type(client_device_id)))

            submitted_user_name = user_name

            if client_device_id is None and submitted_user_name:
                # User is submitting their user name.
                submitted_user_name = str(submitted_user_name).strip()  # Remove excess whitespace.
                new_device_id = generate_id()
                xbmc_log(
                        "Received user name of \"{0}\" for device ID \"{1}\".".format(submitted_user_name,
                                                                                      new_device_id))
                # Update name for respective device ID entry.
                proceed_to_main_page = False
                is_admin = False
                real_admin_pass = "secret-password-here"  # TODO: Remove hard-coded passwords and admin names...
                if any(name in submitted_user_name.lower() for name in ["mrdizzystick", "other admin name"]):
                    # Check for admin password for admin username.
                    # If password is incorrect, boot them back to login page.
                    if admin_pass == real_admin_pass:
                        sql = "UPDATE users SET name = ?, is_admin = ? WHERE device_id = ?"
                        params = [submitted_user_name, True, new_device_id]
                        is_admin = True
                        proceed_to_main_page = True
                    else:
                        xbmc_log("Some phoney tried to log in as admin - username: \"{0}\", pass: \"{1}\".".format(
                                submitted_user_name, admin_pass))
                else:
                    # Any other username.
                    sql = "UPDATE users SET name = ? WHERE device_id = ?"
                    params = [submitted_user_name, new_device_id]
                    proceed_to_main_page = True

                if proceed_to_main_page and sql and params:
                    db.query(sql, params)
                    # User now has device ID and name, send them to the main page.
                    # TODO: Only send to the main page if everything was successful.
                    self.set_cookie("device_id", new_device_id)
                    template = webapp_template_lookup.get_template('main.html')
                    response = template.render(username=submitted_user_name, device_id=new_device_id, is_admin=is_admin)

            elif client_device_id:
                # Client already has a device ID.
                sql = "SELECT id, device_id, given_name, last_name, name, is_admin FROM users WHERE device_id = ?"
                params = [client_device_id]
                results = db.query(sql, params).fetchall()
                xbmc_log("Found {0} records containing the UUID \"{1}\" in the database.".format(len(results),
                                                                                                 client_device_id))

                if len(results) == 0:
                    # Handle edge case where user presents invalid device ID which results in 0 matches.
                    # Clear invalid cookie and redirect client to main route again so they can login properly.
                    xbmc_log(
                            "Unknown UUID \"{0}\" was used by client. Redirecting to login page.".format(
                                    client_device_id))
                    self.delete_cookie("device_id")
                else:
                    # TODO: Make sure only one matching user is allowed per UUID.
                    retreived_id = None
                    retreived_user_name = None
                    is_admin = False

                    for row in results:
                        # If we received any records from the query, use them to get the user name.
                        retreived_id = row['id']
                        retreived_user_name = row['name']
                        is_admin = row['is_admin']

                    if retreived_user_name is not None:
                        # User has device ID and name, send them to the main page.
                        xbmc_log(
                                "Main page view by \"{0}\" (ID: {1}) from device ID \"{2}\".".format(
                                        retreived_user_name,
                                        retreived_id,
                                        client_device_id))
                        template = webapp_template_lookup.get_template('main.html')
                        response = template.render(username=retreived_user_name, device_id=client_device_id,
                                                   is_admin=is_admin)
                    else:
                        # User has device ID but still needs to submit a name.
                        xbmc_log("Login page view by unknown from device ID \"{0}\".".format(client_device_id))
                        self.delete_cookie("device_id")

            else:
                xbmc_log("Client has no device ID yet and has not submitted a name.")

            return response

        @cherrypy.expose
        @cherrypy.tools.json_out()
        def get_data(self):

            client_device_id = self.get_cookie("device_id")  # Get cookie if it exists.
            db = DatabaseManager(database_file)

            full_data = dict()

            # Movie time position.
            real_playback_time = 0  # Default time value.
            if xbmc.Player().isPlaying() and diehard_is_playing:
                real_playback_time = xbmc.Player().getTime()

            # Status of movie playback.
            playback_status = False
            if xbmc.Player().isPlaying() and diehard_is_playing:
                playback_status = True
            playback_is_playing = {"playback_is_playing": playback_status}
            playback_time = {"playback_time": int(real_playback_time)}

            # Total drink count.
            sql = "SELECT COUNT(*) FROM drink_events WHERE executed_at < ?"
            params = [datetime.datetime.now()]
            total_drinks_count = db.query(sql, params).fetchall()[0][0]
            total_drinks = {"total_drinks": total_drinks_count}

            # Time until next drink
            next_drink = {"next_drink": 0}  # Default next drink time.
            if diehard_is_playing:
                sql = "SELECT event_time FROM drink_events WHERE event_time > ? ORDER BY event_time ASC LIMIT 1"
                params = [real_playback_time]
                next_drink_result = db.query(sql, params).fetchone()
                if next_drink_result is not None:
                    next_drink = {"next_drink": int(next_drink_result['event_time'])}

            # Recent drinks / drink history.
            sql = """
                SELECT id, event_time, event_reason, executed_at
                FROM (SELECT * FROM drink_events WHERE event_time <= ? AND executed_at IS NOT NULL ORDER BY event_time DESC LIMIT 4)
                ORDER BY event_time ASC
                """
            params = [real_playback_time]
            recent_drink_result = db.query(sql, params).fetchall()
            recent_drink_result_list = []
            for record in recent_drink_result:
                recent_drink_result_list.append(
                        {
                            "id": record['id'],
                            "event_reason": get_reason_text(record['event_reason']),
                            "executed_at": "{t:%I:%M:%S %p}".format(t=record['executed_at']).lstrip('0')
                        }
                )
            if len(recent_drink_result_list) == 0:
                recent_drink_result_list = [{"event_reason": "None",
                                             "executed_at": "{t:%I:%M:%S %p}".format(t=datetime.datetime.now()).lstrip(
                                                     '0')}]  # Blank recent drink list

            # Recent drink list gets latest 3 entries currently.
            recent_drink_list = {"recent_list": recent_drink_result_list}

            fun = {
                "fun_skill_test": fun_skill_test,
                "fun_snow": fun_snow,
                "fun_brac_logging": fun_brac_logging,
                "fun_led_lighting": fun_led_lighting
            }

            sql = "SELECT device_id, on_piss_break FROM users WHERE device_id = ?"
            params = [client_device_id]
            piss_results = db.query(sql, params).fetchone()
            piss_value = None
            if piss_results is not None:
                piss_value = piss_results['on_piss_break']
            piss_break_status = {"piss_break_status": piss_value}

            # Get execute_at of first and last drinks, then divide by total.
            # TODO: Change this to: get movie start time, get current time, calculate difference, divide total drink count by minutes passed.
            drinks_per_minute = {"drinks_per_minute": 0}
            movie_start_time = db.query(
                    "SELECT action_time FROM users_history WHERE action_type = 'movie_start' ORDER BY action_time DESC LIMIT 1").fetchone()
            xbmc_log("movie_start_time={0}".format(movie_start_time))
            if movie_start_time is not None and len(movie_start_time) > 0:
                total_difference = datetime.datetime.now() - movie_start_time['action_time']
                xbmc_log("total_difference.seconds={0}".format(total_difference.seconds))
                if total_difference.seconds > 0 and total_drinks_count > 0:
                    drinks_per_minute = {"drinks_per_minute": "{0:.1f}".format(
                            total_drinks_count / (float(total_difference.seconds) / 60.0))}

            labels = ["Start"]
            series = [0]
            if diehard_is_playing:
                sql = """
                SELECT strftime('%H:%M', executed_at) AS executed_at_time, (
                    SELECT COUNT(*) FROM drink_events AS t2
                    WHERE t2.executed_at IS NOT NULL AND t2.executed_at <= t1.executed_at
                    ) AS running_total
                FROM drink_events AS t1
                WHERE executed_at IS NOT NULL AND executed_at <= ?
                GROUP BY ((60/5) * strftime('%H', executed_at) + cast((strftime('%M', executed_at) / 5 ) as int))
                ORDER BY executed_at
                """
                params = [datetime.datetime.now()]
                results = db.query(sql, params).fetchall()
                for result in results:
                    result_time = result['executed_at_time']
                    if int(result_time.split(":")[0]) > 12:
                        # If time is 13-24hr, convert to 12-hour time.
                        result_time = "{0}:{1}".format(int(result_time.split(":")[0]) - 12, result_time.split(":")[1])
                    labels.append(result_time)
                    series.append(result['running_total'])
            drinks_over_time_data = {"drinks_over_time": {"labels": labels, "series": [series]}}

            # Chart data.
            labels = ["N/A"]
            series = [0]
            if diehard_is_playing:
                sql = """
                    SELECT name, COUNT(*) as drinks_added
                    FROM drink_events, users
                    WHERE drink_events.created_by = users.id AND drink_events.created_by != 1 AND drink_events.executed_at < ?
                    GROUP BY created_by
                    """
                params = [datetime.datetime.now()]
                results = db.query(sql, params).fetchall()
                if len(results) > 0:
                    labels = []
                    series = []
                    for result in results:
                        user_name = result['name']
                        user_drinks_added = result['drinks_added']
                        labels.append(user_name)
                        series.append(user_drinks_added)
            chart_drinks_submitted_by_user = {"chart_drinks_submitted_by_user": {"labels": labels, "series": series}}

            labels = ["N/A"]
            series = [0]
            if diehard_is_playing:
                sql = """
                    SELECT description_short,
                        (
                        SELECT COUNT(*)
                        FROM drink_events
                        WHERE drink_events.event_reason = drink_reasons.id AND drink_events.executed_at IS NOT NULL AND drink_events.executed_at < ?
                        ) AS running_total_for_type
                    FROM drink_reasons
                    WHERE running_total_for_type > 0
                    GROUP BY drink_reasons.description_short
                    ORDER BY running_total_for_type DESC
                    LIMIT 10
                    """
                params = [datetime.datetime.now()]
                results = db.query(sql, params).fetchall()
                if len(results) > 0:
                    labels = []
                    series = []
                    for result in results:
                        labels.append(result['description_short'])
                        series.append(result['running_total_for_type'])
            chart_drinks_by_type = {"chart_drinks_by_type": {"labels": labels[::-1], "series": series[::-1]}}

            # Drinks by location
            labels = ["N/A"]
            series = [0]
            if diehard_is_playing:
                sql = """
                    SELECT IFNULL(location, 'Other') AS location, COUNT(*) AS cnt
                    FROM drink_events
                    WHERE executed_at < ?
                    GROUP BY location
                    ORDER BY CASE location
                        WHEN 'Roof' THEN 1
                        WHEN '35' THEN 2
                        WHEN '34' THEN 3
                        WHEN '33' THEN 4
                        WHEN '32' THEN 5
                        WHEN '31' THEN 6
                        WHEN '30' THEN 7
                        WHEN '3' THEN 8
                        WHEN 'Lobby' THEN 9
                        WHEN 'Parking' THEN 10
                        WHEN 'Outside' THEN 11
                        WHEN 'Airport' THEN 12
                        ELSE 13 END
                    """
                params = [datetime.datetime.now()]
                results = db.query(sql, params).fetchall()
                if len(results) > 0:
                    labels = []
                    series = []
                    for result in results:
                        labels.append(result['location'])
                        series.append(result['cnt'])
            chart_drinks_by_location = {"chart_drinks_by_location": {"labels": labels[::-1], "series": series[::-1]}}

            labels = ["N/A"]
            series = [0]
            if diehard_is_playing:
                sql = """
                    SELECT users.name, COUNT(*) AS cnt
                    FROM users_history, users
                    WHERE users_history.user_id = users.id AND users_history.action_type = 'piss_start'
                    GROUP BY users.id
                    ORDER BY users.name ASC
                    """
                params = []
                results = db.query(sql, params).fetchall()
                if len(results) > 0:
                    labels = []
                    series = []
                    for result in results:
                        labels.append(result['name'])
                        series.append(result['cnt'])
            chart_number_of_piss_breaks_by_user = {
                "chart_number_of_piss_breaks_by_user": {"labels": labels, "series": series}}

            # Piss break stats
            # chart_piss_break_count_by_user = {"chart_piss_break_count_by_user": {"labels": ["N/A"], "series": [0]}}
            # chart_piss_break_time_by_user = {"chart_piss_break_time_by_user": {"labels": ["N/A"], "series": [0]}}
            # sql = """
            #     SELECT start_log.action_time AS start_time, end_log.action_time AS end_time
            #     FROM users_history AS start_log
            #     INNER JOIN users_history AS end_log ON (start_log.user_id = end_log.user_id AND end_log.action_time > start_log.action_time)
            #     WHERE NOT EXISTS (SELECT 1 FROM users_history WHERE users_history.action_time > start_log.action_time AND users_history.action_time < end_log.action_time)
            #         AND start_log.action_type = 'piss_start'
            #         AND end_log.action_type = 'piss_end'
            #     """
            # params = []
            # results = db.query(sql, params).fetchall()
            # for result in results:
            #     pass

            # Combine everything together for JSON output.
            full_data.update(playback_is_playing)
            full_data.update(playback_time)
            full_data.update(total_drinks)
            full_data.update(next_drink)
            full_data.update(recent_drink_list)
            full_data.update(fun)
            full_data.update(piss_break_status)
            full_data.update(drinks_per_minute)
            full_data.update(drinks_over_time_data)

            # Stats and graph data.
            full_data.update(chart_drinks_submitted_by_user)
            full_data.update(chart_drinks_by_type)
            full_data.update(chart_drinks_by_location)
            full_data.update(chart_number_of_piss_breaks_by_user)

            return full_data

        @cherrypy.expose
        @cherrypy.tools.json_out()
        def action(self, action_request=None):
            # This is how we receive and verify actions requested by clients (e.g. "that's a drink").
            db = DatabaseManager(database_file)
            client_device_id = self.get_cookie("device_id")  # Get cookie if it exists.
            xbmc_log(
                    "Processing action request of \"{0}\" from UUID \"{1}\"...".format(action_request,
                                                                                       client_device_id))
            response = {"ok": False, "reason": "bad"}

            # Verify cookie exists in database, if not then dismiss request.
            sql = "SELECT id, name, given_name, last_name, is_admin, on_piss_break FROM users WHERE device_id = ?"
            params = [client_device_id]
            user_info = db.query(sql, params).fetchall()
            # If we receive only a single user as a result, proceed.
            if len(user_info) == 1:
                if action_request == "drink":
                    # Check for recent drink requests made by this user within the last 5 seonds.
                    sql = "SELECT created_by FROM drink_events WHERE created_by = ? AND executed_at > ?"
                    params = [user_info[0]['id'], datetime.datetime.now() - datetime.timedelta(seconds=5)]
                    drink_request_info = db.query(sql, params).fetchall()
                    xbmc_log("User is making a drink request, they have made {0} recently...".format(
                            len(drink_request_info)))
                    # for request in drink_request_info:
                    #     xbmc_log("id: {0}".format(request[0]))

                    # Prevent user from submitting a drink request if they already have recently.
                    if len(drink_request_info) == 0 and xbmc.Player().isPlaying():
                        sql = "INSERT INTO drink_events (event_time, event_reason, created_by) VALUES (?, ?, ?)"
                        params = [xbmc.Player().getTime(), 1, user_info[0]['id']]
                        # Note: xbmc.Player().getTime() may cause exception here if not currently playing.
                        db.query(sql, params)
                        response = {"ok": True}
                    else:
                        xbmc_log(
                                "Denying drink request from user with UUID \"{0}\": too soon after last request.".format(
                                        client_device_id))
                        response = {"ok": False, "reason": "spam"}

                elif action_request == "piss_break":
                    # Check user's piss break status to determine what we should do.
                    # Not on break = NULL or 0, is on break = 1.
                    user_id = get_user_by_uuid(client_device_id)[0][0]
                    sql = "SELECT device_id, on_piss_break FROM users WHERE device_id = ?"
                    params = [client_device_id]
                    on_piss_break = db.query(sql, params).fetchone()['on_piss_break']

                    if on_piss_break:
                        # End piss break.
                        sql = "INSERT INTO users_history (user_id, action_type, action_time) VALUES (?, ?, ?)"
                        params = [user_id, "piss_end", datetime.datetime.now()]
                        db.query(sql, params)

                        sql = "UPDATE users SET on_piss_break = 0 WHERE device_id = ?"
                        params = [client_device_id]
                        db.query(sql, params)

                        sql = "SELECT user_id, action_type, action_time FROM users_history WHERE user_id = ? AND action_type = ? ORDER BY action_time DESC LIMIT 1"
                        params = [user_id, "piss_start"]
                        piss_start_datetime = db.query(sql, params).fetchone()['action_time']

                        sql = "SELECT COUNT(*) FROM drink_events WHERE executed_at > ? AND executed_at <= ?"
                        params = [piss_start_datetime, datetime.datetime.now()]
                        debt_total = db.query(sql, params).fetchone()[0]

                        # xbmc_log("Debt total for UUID \"{0}\" was: {1}".format(client_device_id, debt_total))
                        response = {"ok": True, "debt": debt_total}

                    else:
                        # Start piss break.
                        sql = "INSERT INTO users_history (user_id, action_type, action_time) VALUES (?, ?, ?)"
                        params = [user_id, "piss_start", datetime.datetime.now()]
                        db.query(sql, params)

                        sql = "UPDATE users SET on_piss_break = 1 WHERE device_id = ?"
                        params = [client_device_id]
                        db.query(sql, params)

                        response = {"ok": True}

                elif "brac_update" in action_request:
                    try:
                        user_id = get_user_by_uuid(client_device_id)[0][0]
                        sql = "INSERT INTO brac_log (user_id, brac, brac_time) VALUES (?, ?, ?)"
                        params = [user_id, float(str(action_request).replace("brac_update")), datetime.datetime.now()]
                        db.query(sql, params)
                    except Exception as e:
                        xbmc_log("ERROR: Exception occurred while trying to add a BRAC entry:")
                        xbmc_log(e)
                    response = {"ok": True}

                elif action_request == "admin_playback_start":
                    if user_info[0]['is_admin']:
                        # Get correct video file name. Check if already playing (what will we do? Ignore play command?).
                        # xbmc.executebuiltin("PlayerControl(RepeatOff)")
                        # Ensure we are at start of lobby music so there's no accidental event triggers.
                        if xbmc.Player().isPlaying():
                            xbmc.Player().seekTime(0)
                        xbmc.Player().play(os.path.join(this_addon_path, "resources", "data", "Die Hard.mkv"))
                        db.query(
                                "INSERT INTO users_history (user_id, action_type, action_time) VALUES (1, 'movie_start', ?)",
                                [datetime.datetime.now()])

                elif action_request == "admin_playback_pause":
                    if user_info[0]['is_admin'] and xbmc.Player().isPlaying():
                        xbmc.Player().pause()  # This toggles pause status.

                elif action_request == "fun_snow":
                    if user_info[0]['is_admin']:
                        global fun_snow
                        fun_snow = not fun_snow
                        xbmc_log("Snow effect is now set to: {0}".format(fun_snow))

                elif action_request == "fun_brac_logging":
                    if user_info[0]['is_admin']:
                        global fun_brac_logging
                        fun_brac_logging = not fun_brac_logging
                        xbmc_log("BRAC logging is now set to: {0}".format(fun_brac_logging))

                elif action_request == "fun_skill_test":
                    if user_info[0]['is_admin']:
                        global fun_skill_test
                        fun_skill_test = not fun_skill_test
                        xbmc_log("Skill-testing question is now set to: {0}".format(fun_skill_test))

                elif action_request == "fun_led_lighting":
                    if user_info[0]['is_admin']:
                        global fun_led_lighting
                        fun_led_lighting = not fun_led_lighting
                        xbmc_log("LED lighting is now set to: {0}".format(fun_led_lighting))

                elif action_request == "username":
                    response = {"ok": True, "username": user_info[0]['name']}

                else:
                    xbmc_log("Received unknown action type \"{0}\" from user with UUID \"{1}\". Ignoring...".format(
                            action_request, client_device_id))
            elif len(user_info) > 1:
                xbmc_log(
                        "Received action request from a UUID with multiple matching users: \"{0}\"! Ignoring...".format(
                                client_device_id))
            else:
                xbmc_log("Received invalid action request from non-existent UUID \"{0}\". Ignoring...".format(
                        client_device_id))

            return response

    diehard_webapp_config = {
        '/': {
            'tools.sessions.on': False,
            'tools.staticdir.root': webroot,
            'tools.staticdir.on': True,
            'tools.staticdir.dir': ''
        }
    }

    reset_drink_history()  # Make sure drink history is set to default state in database.

    # Create XBMC/Kodi GUI.
    dhc_window = xbmcgui.Window(12005)  # Reference existing window "WINDOW_FULLSCREEN_VIDEO".
    # 10000 = Home
    # 12006 = visualization
    dhc_window_visualization = xbmcgui.Window(12006)  # Reference existing window "WINDOW_VISUALISATION".

    # Start playing "Skeletons" by Stevie Wonder, on repeat, as lobby music.
    dhc_lobby_music_playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    dhc_lobby_music_playlist.add(os.path.join(this_addon_path, "resources", "data", "Stevie Wonder - Skeletons.mp3"))
    xbmc.executebuiltin("PlayerControl(RepeatAll)")
    xbmc.Player().play(dhc_lobby_music_playlist)
    xbmc.executebuiltin("ActivateWindow(12006)")  # Switch Kodi to visualization window (12006).
    xbmc.executebuiltin("Action(Info,12006)")  # Try to hide playback control, etc.

    # GUI control coordinates are based on 1280x720 regardless of resolution.
    dhc_window_width = 1280
    dhc_window_height = 720

    # Y position to go for when "in view".
    light_segment_upper_in_y = 0
    light_segment_lower_in_y = dhc_window_height - 125
    # Y position to go for when "out of view".
    light_segment_upper_out_y = -(125 * 2)
    light_segment_lower_out_y = dhc_window_height + 125

    # Greeting message before movie playback, during music visualization. Displays IP address for users to connect to.
    dhc_greeting_vis_label = xbmcgui.ControlLabel(652, 353, 527, 214,
                                                  "Connect to this Wi-Fi network:\n\"{0}\"\n\nPoint your browser to:\nhttp://{1}/\n({2})".format(
                                                          wifi_name, hostname, ipaddress), alignment=6,
                                                  textColor='0xFFFFFFFF', font='font30')
    dhc_greeting_vis_image = xbmcgui.ControlImage(0, 0, dhc_window_width, dhc_window_height,
                                                  os.path.join(imgdir, "lobby-bg-8.png"), colorDiffuse='0xFFFFFFFF')
    dhc_window_visualization.addControl(dhc_greeting_vis_image)
    dhc_window_visualization.addControl(dhc_greeting_vis_label)

    # Final send-off text for at the end of the movie.
    dhc_end_label = xbmcgui.ControlLabel(0, 225, dhc_window_width, dhc_window_height - 450, "Thanks for playing!",
                                         alignment=6, textColor='0xFFFFFFFF',
                                         font='font_MainMenu')  # font35_title / font_MainMenu
    dhc_end_label_bg = xbmcgui.ControlImage(0, 225, dhc_window_width, dhc_window_height - 450,
                                            os.path.join(imgdir, "solid-block.png"), colorDiffuse='0xCC000000')
    dhc_window.addControl(dhc_end_label_bg)  # 0xFFFFFFFF
    dhc_window.addControl(dhc_end_label)  # 0x77000000

    # Decorative string of Christmas lights at top and bottom of screen.
    dhc_deco_lights_top_a = xbmcgui.ControlImage(0, 0, dhc_window_width, 125,
                                                 os.path.join(imgdir, "lights-horizontal.png"), aspectRatio=1)
    dhc_deco_lights_top_b = xbmcgui.ControlImage(dhc_window_width, 0, dhc_window_width, 125,
                                                 os.path.join(imgdir, "lights-horizontal.png"), aspectRatio=1)
    dhc_deco_lights_bottom_a = xbmcgui.ControlImage(0, dhc_window_height - 125, dhc_window_width, 125,
                                                    os.path.join(imgdir, "lights-horizontal.png"), aspectRatio=1)
    dhc_deco_lights_bottom_b = xbmcgui.ControlImage(-dhc_window_width, dhc_window_height - 125, dhc_window_width, 125,
                                                    os.path.join(imgdir, "lights-horizontal.png"), aspectRatio=1)
    dhc_window.addControl(dhc_deco_lights_top_a)
    dhc_window.addControl(dhc_deco_lights_top_b)
    dhc_window.addControl(dhc_deco_lights_bottom_a)
    dhc_window.addControl(dhc_deco_lights_bottom_b)

    # Decorative holly pieces in each corner of screen.
    dhc_deco_holly_top_left = xbmcgui.ControlImage(0, 0, 200, 200, os.path.join(imgdir, "holly-top-left.png"),
                                                   colorDiffuse='0xFFBBBBBB')
    dhc_deco_holly_top_right = xbmcgui.ControlImage(dhc_window_width - 200, 0, 200, 200,
                                                    os.path.join(imgdir, "holly-top-right.png"),
                                                    colorDiffuse='0xFFBBBBBB')
    dhc_deco_holly_bottom_left = xbmcgui.ControlImage(0, dhc_window_height - 200, 200, 200,
                                                      os.path.join(imgdir, "holly-bottom-left.png"),
                                                      colorDiffuse='0xFFBBBBBB')
    dhc_deco_holly_bottom_right = xbmcgui.ControlImage(dhc_window_width - 200, dhc_window_height - 200, 200, 200,
                                                       os.path.join(imgdir, "holly-bottom-right.png"),
                                                       colorDiffuse='0xFFBBBBBB')
    dhc_window.addControl(dhc_deco_holly_top_left)
    dhc_window.addControl(dhc_deco_holly_top_right)
    dhc_window.addControl(dhc_deco_holly_bottom_left)
    dhc_window.addControl(dhc_deco_holly_bottom_right)

    dhc_drink_notification_center_xy = dhc_window_width / 2, dhc_window_height - 140
    dhc_drink_notification_height = 50  # Height of each notification object.

    # Transparent background for the drink event notifications (lower center of screen).
    dhc_drink_notification_bg = xbmcgui.ControlImage(dhc_window_width / 4, dhc_drink_notification_center_xy[
        1] + dhc_drink_notification_height, dhc_window_width / 2, dhc_drink_notification_height,
                                                     os.path.join(imgdir, "solid-block.png"), colorDiffuse='0x77000000')
    dhc_window.addControl(dhc_drink_notification_bg)

    # Initial light effect to verify the connection between the add-on and the LEDs is working.
    send_hyperion_command()

    # The individual drink event notification objects that will be displayed.
    class DrinkEvent(object):
        def __init__(self, event_type=0):
            self.event_type = event_type
            self.text = get_reason_text(event_type).upper()

            # Check for existing drink event with the same type, and if that exists then extend its time and add to combo.
            if len(drink_event_list) > 0 and drink_event_list[len(drink_event_list) - 1].event_type == self.event_type:
                drink_event_list[len(drink_event_list) - 1].add_combo()
            else:
                drink_event_list.append(self)

                self.start_time = datetime.datetime.now()
                self.max_age = 10  # Maximum age in seconds.
                self.end_time = self.start_time + datetime.timedelta(seconds=self.max_age)
                self.total_time = self.end_time - self.start_time
                self.remaining_time = self.end_time - datetime.datetime.now()

                self.remaining_time_total_microseconds = (self.remaining_time.microseconds + (
                    self.remaining_time.seconds + self.remaining_time.days * 24 * 3600) * 10 ** 6)  # / 10**6
                self.total_time_total_microseconds = (self.total_time.microseconds + (
                    self.total_time.seconds + self.total_time.days * 24 * 3600) * 10 ** 6)  # / 10**6
                self.time_percentage = float(self.remaining_time_total_microseconds) / float(self.total_time_total_microseconds)

                self.combo_count = 1
                self.x = 0
                self.y = dhc_window_height  # dhc_drink_notification_center_xy[1] - dhc_drink_notification_height / 2
                self.targetx = self.x  # Position to animate toward.
                self.targety = self.y  # Position to animate toward.
                self.width = dhc_window_width
                self.height = dhc_drink_notification_height
                self.colour = '0xCCFFFFFF'
                self.label = xbmcgui.ControlButton(self.x, self.y, self.width, self.height, self.text, alignment=6,
                                                   font='font30', textColor=self.colour, focusTexture='',
                                                   noFocusTexture='')
                dhc_window.addControl(self.label)
                send_hyperion_command()
            xbmc_log(u"*** Created DrinkEvent - ID: {0}, Text: {1}".format(self.event_type, self.text))

        def tick(self):
            # Actions to perform each step. This will be called by the main loop for each currently-displayed drink notification.

            self.end_time = self.start_time + datetime.timedelta(seconds=self.max_age)
            self.remaining_time = self.end_time - datetime.datetime.now()
            self.total_time = self.end_time - self.start_time

            if self.remaining_time.seconds <= 0:
                self.destroy()  # We've expired.
            else:
                # position = 0
                if self in drink_event_list:
                    self.position = drink_event_list.index(self)
                    self.targety = dhc_drink_notification_center_xy[1] - (dhc_drink_notification_height * self.position)

                if abs(self.y - self.targety) < 2:
                    self.y = self.targety  # If close enough, just snap to final position.

                if self.y < self.targety:
                    self.y += int(math.ceil(abs(float(self.y - self.targety)) / 12))  # Move down.
                elif self.y > self.targety:
                    self.y -= int(math.ceil(abs(float(self.y - self.targety)) / 12))  # Move up.

                # self.time_percentage = self.remaining_time.total_seconds() / self.total_time.total_seconds()  # Only works in Python 2.7+.
                self.remaining_time_total_microseconds = (self.remaining_time.microseconds + (
                    self.remaining_time.seconds + self.remaining_time.days * 24 * 3600) * 10 ** 6)  # / 10**6
                self.total_time_total_microseconds = (self.total_time.microseconds + (
                    self.total_time.seconds + self.total_time.days * 24 * 3600) * 10 ** 6)  # / 10**6
                self.time_percentage = float(self.remaining_time_total_microseconds) / float(self.total_time_total_microseconds)

                self.colour = "0x{0:02X}{1}".format(int(self.time_percentage * 255), self.colour[4:])
                # self.colour = "0xFFFFFFFF"
                if self.combo_count > 1:
                    self.label.setLabel(label=u"{0} × {1}".format(self.text, self.combo_count), textColor=self.colour)
                else:
                    self.label.setLabel(label=u"{0}".format(self.text), textColor=self.colour)
                self.label.setHeight(self.height)
                self.label.setWidth(self.width)
                self.label.setPosition(self.x, self.y)

        def add_combo(self):
            # Reset start time and increase combo counter.
            self.start_time = datetime.datetime.now()
            self.combo_count += 1
            send_hyperion_command()

        def destroy(self):
            # Clean up after ourselves - remove from drink_event_list and remove the control.
            try:
                for drink_event in drink_event_list:
                    if drink_event == self:
                        drink_event_list.remove(self)
            except Exception as e:
                xbmc_log("*** Exception occurred while removing drink event from drink_event_list:")
                xbmc_log(e)

            dhc_window.removeControl(self.label)
            xbmc_log(u"*** Destroyed DrinkEvent - ID: {0}, Text: {1}".format(self.event_type, self.text))

    try:
        # Root access is required to bind ports < 1024 on Mac/Unix systems.
        # Port 8080 might be used by Kodi web server.
        cherrypy.tree.mount(DieHardWebApp(), "/", config=diehard_webapp_config)
        # Server config is separate from application config.
        # Set port, disable log output, disable auto-reload.
        cherrypy.config.update(
                {
                    'server.socket_host': '0.0.0.0',
                    'server.socket_port': int(this_addon.getSetting("dhc_webserver_port")),
                    'log.screen': True,
                    'engine.autoreload.on': False,
                    'response.timeout': 3  # The number of seconds to allow responses to run (default: 300).
                    # 'engine.timeout_monitor.on': False  # TODO: Does this actually help with CherryPy shutdown?
                }
        )
        cherrypy.engine.start()
        xbmc_log("Web server started.")
    except Exception as e:
        xbmc_log("ERROR: Was not able to start the web server.")
        xbmc_log(e)

    pulse_step = 0  # Used with sine calculation to pulse Christmas lights.
    light_movement_speed_max_count = 5
    light_movement_speed_count = 0
    border_enabled = False  # Whether Christmas lights and holly are shown.
    drink_event_list = []  # Holds all currently displayed drink events until they remove themselves.

    db = DatabaseManager(database_file)

    # Keep script running while Kodi has not requested we abort.
    while not xbmc_monitor.abortRequested():
        # Wait for one millisecond to not peg CPU, also check for requests to abort during that time.
        if xbmc_monitor.waitForAbort(0.001):
            break

        xbmc_player_time = 0  # Default player time.

        if xbmc.Player().isPlaying():

            if "mkv" in xbmc.Player().getPlayingFile().lower():  # This includes entire path! Watch out for directory matches!!
                diehard_is_playing = True
                xbmc_player_time = xbmc.Player().getTime()
            else:
                diehard_is_playing = False

            # Only display the ending message when we are at the end of the movie.
            if diehard_is_playing and xbmc_player_time > 7627:
                sql = "SELECT COUNT(*) FROM drink_events WHERE executed_at < ?"
                params = [datetime.datetime.now()]
                total_drinks_count = db.query(sql, params).fetchall()[0][0]
                dhc_end_label.setLabel("Thanks for playing!\n\nTotal drinks consumed: {0}".format(total_drinks_count))
                dhc_end_label.setVisible(True)
                dhc_end_label_bg.setVisible(True)
            else:
                dhc_end_label.setVisible(False)
                dhc_end_label_bg.setVisible(False)

            # Can only get the player time while playing; need player time to determine whether events have occurred or not.
            if diehard_is_playing:
                sql = """
                    SELECT id, event_time, event_reason, executed_at
                    FROM drink_events
                    WHERE event_time <= ? AND executed_at IS NULL
                    """
                params = [xbmc_player_time]
                occurring_events = db.query(sql, params).fetchall()

                # Process drink events.
                if occurring_events is not None:
                    for event in occurring_events:
                        db.query("UPDATE drink_events SET executed_at = ? WHERE id = ?",
                                 (datetime.datetime.now(), event['id']))
                        DrinkEvent(event['event_reason'])

        # Animate decorations and effects.
        pulse_step += (0.05 / 10)
        if pulse_step >= 360:
            pulse_step = 0
        pulse_colour = "0x{0}FFFFFF".format(hex(int(64 + (abs(math.sin(pulse_step)) * 192)))[2:].upper())

        light_movement_speed_count += 1
        if light_movement_speed_count >= light_movement_speed_max_count:
            light_movement_speed_count = 0

        # Scroll segments and wrap around if needed. Set colour.
        # Move toward target Y positions (for transitioning into or out of view).
        try:
            # Upper light segments
            for light_segment_upper in [dhc_deco_lights_top_a, dhc_deco_lights_top_b]:
                if border_enabled:
                    if light_segment_upper.getPosition()[1] < light_segment_upper_in_y:
                        # Move toward target position.
                        target_ypos_upper = light_segment_upper.getPosition()[1] + int(
                                math.ceil(
                                        float(abs(
                                            light_segment_upper.getPosition()[1] - light_segment_upper_in_y)) / 30.0))
                    else:
                        # Set position to final target location.
                        target_ypos_upper = int(light_segment_upper_in_y)
                else:
                    if light_segment_upper.getPosition()[1] > light_segment_upper_out_y:
                        # Move toward target position.
                        target_ypos_upper = light_segment_upper.getPosition()[1] - int(
                                math.ceil(float(
                                        abs(light_segment_upper.getPosition()[1] - light_segment_upper_out_y)) / 30.0))
                    else:
                        # Set position to final target location.
                        target_ypos_upper = int(light_segment_upper_out_y)
                light_segment_upper.setColorDiffuse(pulse_colour)
                if light_movement_speed_count == 0:
                    light_segment_upper.setPosition(light_segment_upper.getPosition()[0] - 1,
                                                    target_ypos_upper)  # Shift left 1 pixel.
                if light_segment_upper.getPosition()[0] <= -dhc_window_width:
                    light_segment_upper.setPosition(dhc_window_width, target_ypos_upper)

            # Lower light segments
            for light_segment_lower in [dhc_deco_lights_bottom_a, dhc_deco_lights_bottom_b]:
                if border_enabled:
                    if light_segment_lower.getPosition()[1] > light_segment_lower_in_y:
                        # Move toward target position.
                        target_ypos_lower = light_segment_lower.getPosition()[1] - int(
                                math.ceil(
                                        float(abs(
                                            light_segment_lower.getPosition()[1] - light_segment_lower_in_y)) / 30.0))
                    else:
                        # Set position to final target location.
                        target_ypos_lower = int(light_segment_lower_in_y)
                else:
                    if light_segment_lower.getPosition()[1] < light_segment_lower_out_y:
                        # Move toward target position.
                        target_ypos_lower = light_segment_lower.getPosition()[1] + int(
                                math.ceil(float(
                                        abs(light_segment_lower.getPosition()[1] - light_segment_lower_out_y)) / 30.0))
                    else:
                        # Set position to final target location.
                        target_ypos_lower = int(light_segment_lower_out_y)
                light_segment_lower.setColorDiffuse(pulse_colour)
                if light_movement_speed_count == 0:
                    light_segment_lower.setPosition(light_segment_lower.getPosition()[0] + 1,
                                                    target_ypos_lower)  # Shift right 1 pixel.
                if light_segment_lower.getPosition()[0] >= dhc_window_width:
                    light_segment_lower.setPosition(-dhc_window_width, target_ypos_lower)

            # Percentage of how far along in the into/out of frame transition we are in (0.0 = out, to 1.0 = in).
            transition_position = (float(dhc_deco_lights_top_a.getPosition()[1] - light_segment_upper_out_y) / float(
                    light_segment_upper_in_y - light_segment_upper_out_y))

            # Upper holly
            for holly_upper in [dhc_deco_holly_top_left, dhc_deco_holly_top_right]:
                holly_upper.setPosition(holly_upper.getPosition()[0],
                                        dhc_deco_lights_top_a.getPosition()[1])  # Snap vertical position to lights.
                holly_upper.setColorDiffuse('0x{0}BBBBBB'.format(
                        hex(int(transition_position * 255))[2:].upper()))  # Fade alpha based on position in transition.

            # Lower holly
            for holly_lower in [dhc_deco_holly_bottom_left, dhc_deco_holly_bottom_right]:
                holly_lower.setPosition(holly_lower.getPosition()[0], dhc_deco_lights_bottom_a.getPosition()[
                    1] + dhc_deco_lights_bottom_a.getHeight() - holly_lower.getHeight())  # Snap vertical position to lights.
                holly_lower.setColorDiffuse('0x{0}BBBBBB'.format(
                        hex(int(transition_position * 255))[2:].upper()))  # Fade alpha based on position in transition.

        except Exception as e:
            xbmc_log("EXCEPTION: Could not update light segment decorations:")
            xbmc_log(e)

        try:
            for drink_event in drink_event_list:
                drink_event.tick()
        except Exception as e:
            xbmc_log("EXCEPTION: Exception occurred while processing drink events:")
            xbmc_log(e)

        try:
            # Drink notification background.
            dhc_drink_notification_bg.setHeight(dhc_drink_notification_height * len(drink_event_list))
            dhc_drink_notification_bg.setPosition(dhc_drink_notification_bg.getPosition()[0],
                                                  dhc_drink_notification_center_xy[
                                                      1] + dhc_drink_notification_height - (
                                                      dhc_drink_notification_height * len(drink_event_list)))
            if len(drink_event_list) > 0:
                border_enabled = True
                dhc_drink_notification_bg.setVisible(True)
            else:
                border_enabled = False
                dhc_drink_notification_bg.setVisible(False)
        except Exception as e:
            xbmc_log("EXCEPTION: Exception occurred while handling drink notification background:")
            xbmc_log(e)

    # All that's left to do is clean up our mess and exit.
    xbmc_log("We've received a request to abort...")
    xbmc_log("Exiting web server...")
    cherrypy.engine.exit()  # TODO: Not sure if this is properly exiting. Still seems to process requests after this.
    xbmc_log("Web server stopped.")


if (__name__ == "__main__"):
    main()
    xbmc.log("*********** Die Hard Christmas ended. ***********")
