import math
import time
import os
import network
import socket
import sys

import app
import settings
from app_components import clear_background
from events.input import BUTTON_TYPES, Buttons

try:
    from .qr import encode as qr_encode
except ImportError:
    from qr import encode as qr_encode


# Settings prefix for namespacing
PREFIX = "conbadge_"

# Keys
KEY_DISPLAY_FIELDS = PREFIX + "display_fields"
KEY_ICE_PHONE = PREFIX + "ice_phone"
KEY_ICE_NAME = PREFIX + "ice_name"
KEY_ICE_NOTES = PREFIX + "ice_notes"


_COLOURS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "silver": (192, 192, 192),
    "maroon": (128, 0, 0),
    "red": (255, 0, 0),
    "purple": (128, 0, 128),
    "fuchsia": (255, 0, 255),
    "green": (0, 128, 0),
    "lime": (0, 255, 0),
    "olive": (128, 128, 0),
    "yellow": (255, 255, 0),
    "navy": (0, 0, 128),
    "blue": (0, 0, 255),
    "teal": (0, 128, 128),
    "aqua": (0, 255, 255),
}

_COLOUR_NAMES = list(_COLOURS.keys())


def _colour_rgb(name, default):
    """Get RGB tuple for a colour name, with fallback."""
    if name and name in _COLOURS:
        return _COLOURS[name]
    return default


def _field_key(name):
    """Get the settings key for a field (prefix all except 'name')."""
    if name == "name":
        return "name"
    return PREFIX + name


def _display_name(key):
    """Strip prefix from a field key for display."""
    if key.startswith(PREFIX):
        return key[len(PREFIX):]
    return key


def _verb_key(field_key):
    """Get the verb settings key for a field."""
    return field_key + "_verb"


def _generate_token():
    """Generate a 4-character hex session token."""
    try:
        raw = os.urandom(2)
        token = ""
        for b in raw:
            token += "{:02x}".format(b)
        return token[:4]
    except Exception:
        import random
        chars = "0123456789abcdef"
        token = ""
        for _ in range(4):
            token += chars[random.randint(0, 15)]
        return token


def _format_exception(e):
    """Format an exception with traceback."""
    import io
    buf = io.StringIO()
    sys.print_exception(e, buf)
    return buf.getvalue()


def _url_decode(s):
    """Decode URL-encoded string."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                result.append(chr(int(s[i+1:i+3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        elif s[i] == '+':
            result.append(' ')
            i += 1
            continue
        result.append(s[i])
        i += 1
    return ''.join(result)


def _parse_form(body):
    """Parse URL-encoded form data."""
    data = {}
    if not body:
        return data
    for pair in body.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            data[_url_decode(key)] = _url_decode(value)
    return data


def _html_esc(s):
    """Escape HTML special characters."""
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class ConferenceBadge(app.App):
    DISPLAY_RADIUS = 120
    AUTO_CYCLE_MS = 5000
    ICE_CONFIRM_TIMEOUT_MS = 5000
    CONFIG_CONFIRM_TIMEOUT_MS = 5000

    FONT_SIZES = [56, 48, 40, 32, 24]
    MIN_FONT_SIZE = 24

    bg_color = (0, 0, 0)
    fg_color = (255, 255, 255)
    header_bg_color = (255, 0, 0)
    header_fg_color = (255, 255, 255)
    ice_bg_color = (255, 0, 0)
    ice_fg_color = (0, 0, 0)

    # App modes
    MODE_SPLASH = 0
    MODE_BADGE = 1
    MODE_WEB_PROMPT = 2
    MODE_WEB_SERVER = 3

    SPLASH_DURATION_MS = 30000

    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)

        # Badge state
        self.current_page = 0
        self.page_timer = 0

        # ICE state
        self.ice_confirm_mode = False
        self.ice_confirm_timer = 0
        self.ice_screen = 0

        # Config confirmation state
        self.config_confirm_mode = False
        self.config_confirm_timer = 0

        # Splash screen state
        self.splash_timer = 0

        # Web server state
        self.mode = self.MODE_SPLASH
        self.server_socket = None
        self.session_token = ""
        self.ip_address = None
        self.server_url = ""
        self.qr_matrix = None

        # Load settings
        self._load_settings()

    def _load_settings(self):
        """Load display fields and values from settings."""
        self.display_fields = settings.get(KEY_DISPLAY_FIELDS)
        if self.display_fields is None:
            self.display_fields = ["name"]
            settings.set(KEY_DISPLAY_FIELDS, self.display_fields)

        self.ice_phone = settings.get(KEY_ICE_PHONE)
        self.ice_name = settings.get(KEY_ICE_NAME)
        self.ice_notes = settings.get(KEY_ICE_NOTES)

    def _has_settings(self):
        """Check if any meaningful settings are configured."""
        # Check if name is set
        if settings.get("name"):
            return True
        # Check if any conbadge_ field has a value
        for field in self.display_fields:
            if field != "name" and settings.get(field):
                return True
        return False

    def _has_ice_configured(self):
        return self.ice_phone or self.ice_name

    def _get_field_value(self, field_key):
        return settings.get(field_key)

    def _get_field_label(self, field_key):
        return _display_name(field_key)

    def _get_field_verb(self, field_key):
        verb = settings.get(_verb_key(field_key))
        if verb:
            return verb
        return "is"

    def get_usable_width(self, y):
        if abs(y) >= self.DISPLAY_RADIUS:
            return 0
        return 2 * math.sqrt(self.DISPLAY_RADIUS ** 2 - y ** 2)

    def fit_text(self, ctx, text, y_position, max_width=None):
        if max_width is None:
            max_width = self.get_usable_width(y_position)
        max_width = max_width * 0.9
        if max_width <= 0:
            return self.MIN_FONT_SIZE, [text]
        for font_size in self.FONT_SIZES:
            ctx.font_size = font_size
            if ctx.text_width(text) <= max_width:
                return font_size, [text]
        ctx.font_size = self.MIN_FONT_SIZE
        return self.MIN_FONT_SIZE, self._wrap_text(ctx, text, max_width)

    def _wrap_text(self, ctx, text, max_width):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = (current_line + " " + word).strip()
            if ctx.text_width(test_line) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines if lines else [text]

    # --- Web Server ---

    def _start_web_server(self):
        """Start the web server and generate QR code."""
        self.session_token = _generate_token()

        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            return False

        self.ip_address = wlan.ifconfig()[0]
        self.port = 8989
        self.server_url = "http://" + self.ip_address + ":" + str(self.port) + "/" + self.session_token

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(1)
            self.server_socket.setblocking(False)
        except Exception as e:
            print("Server start error: " + str(e))
            return False

        # Generate QR code
        try:
            self.qr_matrix = qr_encode(self.server_url)
        except Exception as e:
            print("QR encode error: " + str(e))

        self.mode = self.MODE_WEB_SERVER
        return True

    def _stop_web_server(self):
        """Stop the web server."""
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        self.mode = self.MODE_BADGE
        self.qr_matrix = None
        self._load_settings()

    def _poll_server(self):
        """Check for incoming HTTP requests (non-blocking)."""
        if not self.server_socket:
            return
        try:
            client, addr = self.server_socket.accept()
            self._handle_request(client)
        except OSError:
            pass

    def _handle_request(self, client):
        """Handle an incoming HTTP request."""
        try:
            request = client.recv(4096).decode('utf-8')
            if not request:
                client.close()
                return

            lines = request.split('\r\n')
            first_line = lines[0] if lines else ""
            parts = first_line.split(' ')
            method = parts[0] if parts else "GET"
            path = parts[1] if len(parts) > 1 else "/"

            # Check session token
            if path != "/" + self.session_token and not path.startswith("/" + self.session_token + "?"):
                error_body = '''<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body { font-family: sans-serif; text-align: center; padding: 50px 20px; }
h1 { color: #a94442; } .msg { background: #f2dede; padding: 20px; border-radius: 8px; color: #a94442; max-width: 400px; margin: 20px auto; }</style>
</head><body><h1>Access Denied</h1><div class="msg">Failed to access the config page. The session token in the URL is invalid.</div>
<p>Scan the QR code on the badge to get the correct URL.</p></body></html>'''
                response = "HTTP/1.1 403 Forbidden\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + error_body
                client.send(response.encode('utf-8'))
                client.close()
                return

            # Get body for POST
            body = ""
            if method == "POST":
                body_start = request.find('\r\n\r\n')
                if body_start != -1:
                    body = request[body_start + 4:]

            # Process request
            if method == "POST":
                response_body = self._handle_post(body)
            else:
                response_body = self._get_settings_page()

            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + response_body
            client.send(response.encode('utf-8'))

        except Exception as e:
            tb = _format_exception(e)
            print("Request error: " + str(e) + "\n" + tb)
            try:
                error_page = self._get_error_page(str(e), tb)
                response = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + error_page
                client.send(response.encode('utf-8'))
            except:
                pass
        finally:
            client.close()

    def _handle_post(self, body):
        """Handle POST form submission."""
        try:
            data = _parse_form(body)
            display_fields = settings.get(KEY_DISPLAY_FIELDS) or ["name"]
            message = "Settings saved!"

            # Handle delete
            if "delete" in data:
                field_to_delete = data["delete"]
                if field_to_delete in display_fields and field_to_delete != "name":
                    display_fields.remove(field_to_delete)
                    settings.set(KEY_DISPLAY_FIELDS, display_fields)
                    settings.set(field_to_delete, "")
                    settings.set(_verb_key(field_to_delete), "")
                    for suffix in ["_hbg", "_hfg", "_vbg", "_vfg"]:
                        settings.set(field_to_delete + suffix, "")
                    message = "Deleted field: " + _display_name(field_to_delete)

            # Handle add field
            elif data.get("action") == "add_field" and data.get("new_field"):
                raw_name = data["new_field"].strip().lower().replace(" ", "_")
                field_key = _field_key(raw_name)
                if field_key and field_key not in display_fields:
                    display_fields.append(field_key)
                    settings.set(KEY_DISPLAY_FIELDS, display_fields)
                    message = "Added field: " + raw_name

            # Handle move up
            elif "move_up" in data:
                try:
                    idx = int(data["move_up"])
                    if idx > 0 and idx < len(display_fields):
                        display_fields[idx], display_fields[idx-1] = display_fields[idx-1], display_fields[idx]
                        settings.set(KEY_DISPLAY_FIELDS, display_fields)
                        message = "Field moved up"
                except (ValueError, IndexError):
                    pass

            # Handle move down
            elif "move_down" in data:
                try:
                    idx = int(data["move_down"])
                    if idx >= 0 and idx < len(display_fields) - 1:
                        display_fields[idx], display_fields[idx+1] = display_fields[idx+1], display_fields[idx]
                        settings.set(KEY_DISPLAY_FIELDS, display_fields)
                        message = "Field moved down"
                except (ValueError, IndexError):
                    pass

            # Handle save all
            elif data.get("action") == "save":
                for field in display_fields:
                    value_key = "value_" + field
                    verb_k = "verb_" + field

                    if value_key in data and field != "name":
                        settings.set(field, data[value_key])

                    if verb_k in data:
                        verb = data[verb_k]
                        if verb == "are":
                            settings.set(_verb_key(field), verb)
                        else:
                            settings.set(_verb_key(field), "")

                    # Save colour settings
                    for suffix in ["hbg", "hfg", "vbg", "vfg"]:
                        form_key = suffix + "_" + field
                        if form_key in data and data[form_key] in _COLOUR_NAMES:
                            settings.set(field + "_" + suffix, data[form_key])

                # Save ICE settings
                settings.set(KEY_ICE_PHONE, data.get("ice_phone", ""))
                settings.set(KEY_ICE_NAME, data.get("ice_name", ""))
                settings.set(KEY_ICE_NOTES, data.get("ice_notes", ""))

                message = "All settings saved!"

            try:
                settings.save()
            except Exception as e:
                print("Save error: " + str(e))

            self._load_settings()
            return self._get_success_page(message)

        except Exception as e:
            tb = _format_exception(e)
            print("POST error: " + str(e) + "\n" + tb)
            return self._get_error_page(str(e), tb)

    def _get_settings_page(self):
        """Generate the settings HTML page."""
        display_fields = settings.get(KEY_DISPLAY_FIELDS) or ["name"]

        field_rows = ""
        for field in display_fields:
            value = settings.get(field) or ""
            verb = settings.get(_verb_key(field)) or "is"
            is_sel = "selected" if verb == "is" else ""
            are_sel = "selected" if verb == "are" else ""
            disp_name = _html_esc(_display_name(field))
            esc_field = _html_esc(field)
            esc_value = _html_esc(value)

            hbg = settings.get(field + "_hbg") or "red"
            hfg = settings.get(field + "_hfg") or "white"
            vbg = settings.get(field + "_vbg") or "black"
            vfg = settings.get(field + "_vfg") or "white"

            is_name = (field == "name")
            readonly = " readonly" if is_name else ""
            value_input = '<input type="text" name="value_' + esc_field + '" value="' + esc_value + '"' + readonly + '>'
            delete_btn = "" if is_name else '<button type="submit" name="delete" value="' + esc_field + '">Delete</button>'

            field_rows += '''
            <tr>
                <td>
                    my <b>''' + disp_name + '''</b>
                    <select class="verb" name="verb_''' + esc_field + '''">
                        <option value="is" ''' + is_sel + '''>is</option>
                        <option value="are" ''' + are_sel + '''>are</option>
                    </select>
                    <span class="cbox" id="box_hbg_''' + esc_field + '''" style="background:''' + hbg + '''" onclick="openPicker(''' + "'" + '''hbg_''' + esc_field + "'" + ''')">B</span>
                    <span class="cbox" id="box_hfg_''' + esc_field + '''" style="background:''' + hfg + '''" onclick="openPicker(''' + "'" + '''hfg_''' + esc_field + "'" + ''')">F</span>
                    <input type="hidden" name="hbg_''' + esc_field + '''" id="hbg_''' + esc_field + '''" value="''' + hbg + '''">
                    <input type="hidden" name="hfg_''' + esc_field + '''" id="hfg_''' + esc_field + '''" value="''' + hfg + '''">
                </td>
            </tr>
            <tr>
                <td>
                    ''' + value_input + '''
                    <span class="cbox" id="box_vbg_''' + esc_field + '''" style="background:''' + vbg + '''" onclick="openPicker(''' + "'" + '''vbg_''' + esc_field + "'" + ''')">B</span>
                    <span class="cbox" id="box_vfg_''' + esc_field + '''" style="background:''' + vfg + '''" onclick="openPicker(''' + "'" + '''vfg_''' + esc_field + "'" + ''')">F</span>
                    <input type="hidden" name="vbg_''' + esc_field + '''" id="vbg_''' + esc_field + '''" value="''' + vbg + '''">
                    <input type="hidden" name="vfg_''' + esc_field + '''" id="vfg_''' + esc_field + '''" value="''' + vfg + '''">
                </td>
            </tr>
            <tr>
                <td>''' + delete_btn + '''</td>
            </tr>'''

        ice_phone = _html_esc(settings.get(KEY_ICE_PHONE) or "")
        ice_name = _html_esc(settings.get(KEY_ICE_NAME) or "")
        ice_notes = _html_esc(settings.get(KEY_ICE_NOTES) or "")

        # Reorder section
        reorder_html = ""
        if len(display_fields) > 1:
            for i, field in enumerate(display_fields):
                disp = _html_esc(_display_name(field))
                idx_str = str(i)
                up_dis = "disabled" if i == 0 else ""
                down_dis = "disabled" if i == len(display_fields) - 1 else ""
                reorder_html += '''
                <div style="margin: 5px 0;">
                    <span style="display: inline-block; width: 150px;">''' + disp + '''</span>
                    <button type="submit" name="move_up" value="''' + idx_str + '''" ''' + up_dis + '''>Up</button>
                    <button type="submit" name="move_down" value="''' + idx_str + '''" ''' + down_dis + '''>Down</button>
                </div>'''
        else:
            reorder_html = "<p>Add more fields to reorder.</p>"

        action_url = "/" + self.session_token

        return '''<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Badge Settings</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 15px; }
        h1 { color: #333; font-size: 24px; margin-bottom: 20px; }
        h2 { color: #333; font-size: 18px; margin: 15px 0 10px 0; }
        h3 { font-size: 16px; margin: 15px 0 10px 0; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { padding: 12px 8px; text-align: left; border-bottom: 1px solid #ddd; }
        input[type="text"], select { width: 100%; padding: 12px; box-sizing: border-box; font-size: 16px; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 12px 20px; margin: 8px 4px; cursor: pointer; font-size: 16px; border-radius: 4px; }
        .save-btn { background: #4CAF50; color: white; border: none; width: 100%; margin-top: 15px; }
        .add-btn { background: #2196F3; color: white; border: none; }
        .section { background: #f9f9f9; padding: 15px; margin: 15px 0; border-radius: 8px; }
        select { background: white; }
        select.verb { width: auto; display: inline; padding: 4px 8px; }
        .cbox { display: inline-block; width: 24px; height: 24px; border: 2px solid #333; border-radius: 4px; cursor: pointer; text-align: center; line-height: 24px; font-size: 11px; font-weight: bold; vertical-align: middle; margin-left: 4px; color: white; text-shadow: 0 0 2px black, 0 0 2px black; }
        #colorModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 999; align-items: center; justify-content: center; }
        .cpicker { background: white; padding: 20px; border-radius: 8px; text-align: center; max-width: 300px; }
        .cbtn { display: inline-block; width: 36px; height: 36px; margin: 4px; border: 2px solid #333; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Badge Settings</h1>

    <form method="POST" action="''' + action_url + '''">
        <div class="section">
            <h2>Display Fields</h2>
            <table>
                <tr><th>Screen shows</th></tr>
                ''' + field_rows + '''
            </table>
            <h3>Add Field</h3>
            <input type="text" name="new_field" placeholder="e.g. email, pronouns, company">
            <button type="submit" name="action" value="add_field" class="add-btn">Add</button>
        </div>

        <div class="section">
            <h2>ICE (Emergency Contact)</h2>
            <table>
                <tr><td>Phone:</td><td><input type="text" name="ice_phone" value="''' + ice_phone + '''"></td></tr>
                <tr><td>Name:</td><td><input type="text" name="ice_name" value="''' + ice_name + '''"></td></tr>
                <tr><td>Notes:</td><td><input type="text" name="ice_notes" value="''' + ice_notes + '''" placeholder="e.g. allergies, conditions, medication"></td></tr>
            </table>
        </div>

        <button type="submit" name="action" value="save" class="save-btn">Save All Settings</button>
    </form>

    <div class="section">
        <h2>Reorder</h2>
        <form method="POST" action="''' + action_url + '''">
            ''' + reorder_html + '''
        </form>
    </div>

    <p style="text-align:center;margin-top:20px;"><a href="https://github.com/JonTheNiceGuy/tildagon-my-conference-badge">GitHub</a></p>

    <div id="colorModal" onclick="closeModal()">
        <div class="cpicker" onclick="event.stopPropagation()">
            <p><b>Pick a colour</b></p>
            <div id="colorBtns"></div>
            <p style="margin-top:10px;"><button type="button" onclick="closeModal()">Cancel</button></p>
        </div>
    </div>

    <script>
    var activeInput=null;
    var colors=["black","white","gray","silver","maroon","red","purple","fuchsia","green","lime","olive","yellow","navy","blue","teal","aqua"];
    var btns="";
    for(var i=0;i<colors.length;i++){
        btns+='<span class="cbtn" style="background:'+colors[i]+'" data-color="'+colors[i]+'"></span>';
    }
    document.getElementById("colorBtns").innerHTML=btns;
    document.getElementById("colorBtns").addEventListener("click",function(e){
        if(e.target.dataset.color){pickColor(e.target.dataset.color);}
    });
    function openPicker(id){activeInput=id;document.getElementById("colorModal").style.display="flex";}
    function closeModal(){document.getElementById("colorModal").style.display="none";}
    function pickColor(c){
        document.getElementById(activeInput).value=c;
        document.getElementById("box_"+activeInput).style.background=c;
        closeModal();
    }
    </script>
</body>
</html>'''

    def _get_success_page(self, message):
        url = "/" + self.session_token
        return '''<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="1;url=''' + url + '''">
<style>body { font-family: sans-serif; text-align: center; padding: 50px; }
.ok { background: #dff0d8; padding: 20px; border-radius: 5px; color: #3c763d; }</style>
</head><body><div class="ok">''' + _html_esc(message) + '''</div><p>Redirecting...</p></body></html>'''

    def _get_error_page(self, error, tb=""):
        tb_html = ""
        if tb:
            tb_html = '<pre style="background:#333;color:#fff;padding:10px;overflow-x:auto;">' + _html_esc(tb) + '</pre>'
        url = "/" + self.session_token
        return '''<!DOCTYPE html>
<html><head><style>body { font-family: sans-serif; padding: 20px; }
.err { background: #f2dede; padding: 20px; border-radius: 5px; color: #a94442; }</style>
</head><body><h1>Error</h1><div class="err">''' + _html_esc(error) + '''</div>''' + tb_html + '''
<p><a href="''' + url + '''">Back</a></p></body></html>'''

    # --- Main Loop ---

    async def run(self, render_update):
        last_time = time.ticks_ms()
        while True:
            cur_time = time.ticks_ms()
            delta = time.ticks_diff(cur_time, last_time)
            last_time = cur_time

            if self.mode == self.MODE_WEB_SERVER:
                self._poll_server()

            self.update(delta)
            await render_update()

    def update(self, delta):
        self._load_settings()

        if self.mode == self.MODE_SPLASH:
            self._update_splash(delta)
        elif self.mode == self.MODE_BADGE:
            self._update_badge(delta)
        elif self.mode == self.MODE_WEB_PROMPT:
            self._update_web_prompt()
        elif self.mode == self.MODE_WEB_SERVER:
            self._update_web_server()

    def _update_badge(self, delta):
        """Update badge display mode."""
        self.page_timer += delta
        if self.ice_confirm_mode:
            self.ice_confirm_timer += delta
        if self.config_confirm_mode:
            self.config_confirm_timer += delta

        # ICE confirmation timeout
        if self.ice_confirm_mode and self.ice_confirm_timer >= self.ICE_CONFIRM_TIMEOUT_MS:
            self.ice_confirm_mode = False
            self.ice_confirm_timer = 0

        # Config confirmation timeout
        if self.config_confirm_mode and self.config_confirm_timer >= self.CONFIG_CONFIRM_TIMEOUT_MS:
            self.config_confirm_mode = False
            self.config_confirm_timer = 0

        # Auto-advance pages (only when not in any confirmation mode)
        if not self.ice_confirm_mode and not self.config_confirm_mode and self.ice_screen == 0:
            if self.page_timer >= self.AUTO_CYCLE_MS:
                self._next_page()
                self.page_timer = 0

        # Cancel button
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            if self.ice_screen > 0:
                self.ice_screen = 0
            elif self.ice_confirm_mode:
                self.ice_confirm_mode = False
                self.ice_confirm_timer = 0
            elif self.config_confirm_mode:
                self.config_confirm_mode = False
                self.config_confirm_timer = 0
            else:
                self.minimise()
            self.button_states.clear()

        # Confirm (C) - next page
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            if not self.ice_confirm_mode and not self.config_confirm_mode and self.ice_screen == 0:
                self._next_page()
                self.page_timer = 0
            self.button_states.clear()

        # Left (E) - prev page or confirm ICE/config
        if self.button_states.get(BUTTON_TYPES["LEFT"]):
            if self.ice_confirm_mode:
                self.ice_confirm_mode = False
                self.ice_confirm_timer = 0
                self.ice_screen = 1
            elif self.config_confirm_mode:
                self.config_confirm_mode = False
                self.config_confirm_timer = 0
                if not self._start_web_server():
                    # WiFi not available, go to prompt
                    self.mode = self.MODE_WEB_PROMPT
            elif self.ice_screen == 0:
                self._prev_page()
                self.page_timer = 0
            self.button_states.clear()

        # Right (B) - ICE mode
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            if self.ice_screen == 0 and not self.ice_confirm_mode and not self.config_confirm_mode:
                self.ice_confirm_mode = True
                self.ice_confirm_timer = 0
            elif self.ice_screen == 1:
                self.ice_screen = 2
            elif self.ice_screen == 2:
                self.ice_screen = 0
            self.button_states.clear()

        # Down (D) - Config mode
        if self.button_states.get(BUTTON_TYPES["DOWN"]):
            if self.ice_screen == 0 and not self.ice_confirm_mode and not self.config_confirm_mode:
                self.config_confirm_mode = True
                self.config_confirm_timer = 0
            self.button_states.clear()

    def _update_web_prompt(self):
        """Update web server prompt mode."""
        # B to confirm start
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.button_states.clear()
            if not self._start_web_server():
                # WiFi not available, stay in prompt
                pass

        # Cancel to go back
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.mode = self.MODE_BADGE

    def _update_web_server(self):
        """Update web server mode."""
        # Cancel to stop server
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self._stop_web_server()

    def _update_splash(self, delta):
        """Update splash screen mode."""
        self.splash_timer += delta

        # Auto-dismiss after duration
        if self.splash_timer >= self.SPLASH_DURATION_MS:
            self._end_splash()
            return

        # Any button press dismisses splash
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]) or \
           self.button_states.get(BUTTON_TYPES["CANCEL"]) or \
           self.button_states.get(BUTTON_TYPES["UP"]) or \
           self.button_states.get(BUTTON_TYPES["DOWN"]) or \
           self.button_states.get(BUTTON_TYPES["LEFT"]) or \
           self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.button_states.clear()
            self._end_splash()

    def _end_splash(self):
        """End splash screen and go to appropriate mode."""
        self.splash_timer = 0
        # Auto-start web server if no settings configured
        if not self._has_settings():
            self.mode = self.MODE_WEB_PROMPT
            if self._start_web_server():
                pass  # Will show QR code
        else:
            self.mode = self.MODE_BADGE

    def _next_page(self):
        if self.display_fields:
            self.current_page = (self.current_page + 1) % len(self.display_fields)

    def _prev_page(self):
        if self.display_fields:
            self.current_page = (self.current_page - 1) % len(self.display_fields)

    # --- Drawing ---

    def draw(self, ctx):
        clear_background(ctx)
        ctx.text_align = ctx.CENTER
        ctx.font = "Arimo Bold"

        if self.mode == self.MODE_SPLASH:
            self._draw_splash(ctx)
        elif self.mode == self.MODE_WEB_PROMPT:
            self._draw_web_prompt(ctx)
        elif self.mode == self.MODE_WEB_SERVER:
            self._draw_web_server(ctx)
        elif self.ice_confirm_mode:
            self._draw_ice_confirm(ctx)
        elif self.config_confirm_mode:
            self._draw_config_confirm(ctx)
        elif self.ice_screen > 0:
            self._draw_ice_screen(ctx)
        else:
            self._draw_badge_page(ctx)

        self.draw_overlays(ctx)

    def _draw_splash(self, ctx):
        """Draw splash screen with button instructions."""
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)

        # Title
        ctx.font_size = 22
        ctx.move_to(0, -90).text("My")
        ctx.move_to(0, -68).text("Conference")
        ctx.move_to(0, -46).text("Badge")

        # Instructions
        ctx.font_size = 18
        ctx.move_to(0, -20).text("Press B for ICE info")
        ctx.move_to(0, 5).text("Press D for config")
        ctx.font_size = 16
        ctx.rgb(200, 200, 200)
        ctx.move_to(0, 35).text("Then press E to confirm")

        # Countdown
        remaining = (self.SPLASH_DURATION_MS - self.splash_timer) / 1000
        ctx.font_size = 16
        ctx.rgb(150, 150, 150)
        remaining_str = str(int(remaining))
        ctx.move_to(0, 70).text("Any button to continue")
        ctx.move_to(0, 95).text("(" + remaining_str + "s)")

    def _draw_web_prompt(self, ctx):
        """Draw web server start prompt."""
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)
        ctx.font_size = 24
        ctx.move_to(0, -40).text("Start Web Settings?")
        ctx.font_size = 20
        ctx.move_to(0, 0).text("Press B to start")
        ctx.move_to(0, 30).text("Press F to cancel")
        ctx.rgb(150, 150, 150)
        ctx.font_size = 14
        ctx.move_to(0, 70).text("Requires WiFi connection")

    def _draw_web_server(self, ctx):
        """Draw web server screen with QR code."""
        ctx.rgb(255, 255, 255).rectangle(-120, -120, 240, 240).fill()

        qr_bottom = 60
        if self.qr_matrix:
            qr_size = len(self.qr_matrix)
            pixel_size = min(160 // qr_size, 5)
            total_size = qr_size * pixel_size
            offset_x = -total_size // 2
            offset_y = -total_size // 2 - 25

            for r in range(qr_size):
                for c in range(qr_size):
                    if self.qr_matrix[r][c]:
                        x = offset_x + c * pixel_size
                        y = offset_y + r * pixel_size
                        ctx.rgb(0, 0, 0).rectangle(x, y, pixel_size, pixel_size).fill()

            qr_bottom = offset_y + total_size + 12 + 4

        # URL just below QR code
        ctx.rgb(255, 0, 0)
        font_size, _ = self.fit_text(ctx, self.server_url, qr_bottom)
        ctx.font_size = min(font_size, 16)
        ctx.move_to(0, qr_bottom).text(self.server_url)

        ctx.font_size = 16
        ctx.move_to(0, qr_bottom + 20).text("F to stop server")

    def _get_field_colours(self, field_key):
        """Get per-field colours, falling back to defaults."""
        hbg = _colour_rgb(settings.get(field_key + "_hbg"), self.header_bg_color)
        hfg = _colour_rgb(settings.get(field_key + "_hfg"), self.header_fg_color)
        vbg = _colour_rgb(settings.get(field_key + "_vbg"), self.bg_color)
        vfg = _colour_rgb(settings.get(field_key + "_vfg"), self.fg_color)
        return hbg, hfg, vbg, vfg

    def _draw_badge_page(self, ctx):
        """Draw a normal badge page."""
        if not self.display_fields:
            ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
            self._draw_no_fields(ctx)
            return

        field_key = self.display_fields[self.current_page]
        field_value = self._get_field_value(field_key)
        field_label = self._get_field_label(field_key)
        verb = self._get_field_verb(field_key)
        hbg, hfg, vbg, vfg = self._get_field_colours(field_key)

        ctx.rgb(*vbg).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(*hbg).rectangle(-120, -120, 240, 100).fill()

        # Header
        ctx.font_size = 56
        ctx.rgb(*hfg).move_to(0, -60).text("Hello")
        ctx.font_size = 28
        ctx.rgb(*hfg).move_to(0, -30).text("my " + field_label + " " + verb)

        # Value
        if field_value:
            font_size, lines = self.fit_text(ctx, field_value, 60)
            ctx.font_size = font_size
            ctx.rgb(*vfg)
            line_height = font_size * 1.2
            total_height = line_height * len(lines)
            start_y = 60 - (total_height / 2) + (line_height / 2)
            for i, line in enumerate(lines):
                y = start_y + (i * line_height)
                ctx.move_to(0, y).text(line)
        else:
            ctx.font_size = 20
            ctx.font = "Arimo Italic"
            ctx.rgb(*vfg).move_to(0, 40).text("Not set")
            ctx.move_to(0, 65).text("Press D for settings")

        if len(self.display_fields) > 1:
            self._draw_page_indicator(ctx, vfg)

    def _draw_no_fields(self, ctx):
        ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 20
        ctx.font = "Arimo Italic"
        ctx.rgb(*self.fg_color).move_to(0, -10).text("No fields configured")
        ctx.move_to(0, 20).text("Press D for settings")

    def _draw_page_indicator(self, ctx, active_color):
        num_pages = len(self.display_fields)
        dot_radius = 4
        dot_spacing = 15
        total_width = (num_pages - 1) * dot_spacing
        start_x = -total_width / 2
        y = 105
        for i in range(num_pages):
            x = start_x + (i * dot_spacing)
            if i == self.current_page:
                ctx.rgb(*active_color)
            else:
                ctx.rgb(100, 100, 100)
            ctx.arc(x, y, dot_radius, 0, 2 * math.pi, True).fill()

    def _draw_ice_confirm(self, ctx):
        ctx.rgb(*self.ice_bg_color).rectangle(-120, -120, 240, 240).fill()
        if not self._has_ice_configured():
            ctx.font_size = 24
            ctx.rgb(*self.ice_fg_color).move_to(0, -20).text("ICE not configured")
            ctx.font_size = 18
            ctx.move_to(0, 20).text("Press D for settings")
            return
        ctx.font_size = 32
        ctx.rgb(*self.ice_fg_color).move_to(0, -40).text("Display ICE?")
        ctx.font_size = 24
        ctx.move_to(0, 10).text("Press E to confirm")
        remaining = (self.ICE_CONFIRM_TIMEOUT_MS - self.ice_confirm_timer) / 1000
        ctx.font_size = 20
        remaining_str = str(int(remaining * 10) / 10) + "s"
        ctx.move_to(0, 50).text("(" + remaining_str + ")")

    def _draw_config_confirm(self, ctx):
        ctx.rgb(0, 0, 100).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)
        ctx.font_size = 28
        ctx.move_to(0, -40).text("Enter Config Mode?")
        ctx.font_size = 24
        ctx.move_to(0, 10).text("Press E to confirm")
        remaining = (self.CONFIG_CONFIRM_TIMEOUT_MS - self.config_confirm_timer) / 1000
        ctx.font_size = 20
        remaining_str = str(int(remaining * 10) / 10) + "s"
        ctx.move_to(0, 50).text("(" + remaining_str + ")")

    def _draw_ice_screen(self, ctx):
        ctx.rgb(*self.ice_bg_color).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 32
        ctx.rgb(*self.ice_fg_color).move_to(0, -80).text("ICE")

        if self.ice_screen == 1:
            ctx.font_size = 20
            ctx.move_to(0, -40).text("Emergency Contact")
            if self.ice_name:
                font_size, lines = self.fit_text(ctx, self.ice_name, 0)
                ctx.font_size = min(font_size, 28)
                ctx.move_to(0, 0).text(self.ice_name)
            if self.ice_phone:
                font_size, lines = self.fit_text(ctx, self.ice_phone, 40)
                ctx.font_size = min(font_size, 28)
                ctx.move_to(0, 40).text(self.ice_phone)
            ctx.font_size = 16
            ctx.move_to(0, 90).text("B: notes | F: exit")
        elif self.ice_screen == 2:
            ctx.font_size = 20
            ctx.move_to(0, -40).text("Medical Notes")
            if self.ice_notes:
                font_size, lines = self.fit_text(ctx, self.ice_notes, 20, max_width=200)
                ctx.font_size = min(font_size, 24)
                line_height = ctx.font_size * 1.2
                start_y = 10
                for i, line in enumerate(lines[:4]):
                    y = start_y + (i * line_height)
                    ctx.move_to(0, y).text(line)
            else:
                ctx.font_size = 20
                ctx.move_to(0, 20).text("No notes set")
            ctx.font_size = 16
            ctx.move_to(0, 90).text("B/F: exit")


__app_export__ = ConferenceBadge
