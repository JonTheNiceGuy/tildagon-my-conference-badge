"""Helper functions and constants for Conference Badge app."""

import os
import sys

# Settings prefix for namespacing
PREFIX = "conbadge_"

# Keys
KEY_DISPLAY_FIELDS = PREFIX + "display_fields"
KEY_NAME = PREFIX + "name"
KEY_HAS_STARTED = PREFIX + "has_started"
KEY_ICE_PHONE = PREFIX + "ice_phone"
KEY_ICE_NAME = PREFIX + "ice_name"
KEY_ICE_NOTES = PREFIX + "ice_notes"

# Image constants
IMAGE_FILENAME = "badge_image.jpg"
IMAGE_FIELD = "__image__"

# Event logo (built-in image)
EVENT_LOGO_FILENAME = "event_logo.jpg"
EVENT_LOGO_FIELD = "__event_logo__"

# Colour definitions (16 HTML named colours)
COLOURS = {
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

COLOUR_NAMES = list(COLOURS.keys())


def colour_rgb(name, default):
    """Get RGB tuple for a colour name, with fallback."""
    if name and name in COLOURS:
        return COLOURS[name]
    return default


def field_key(name):
    """Get the settings key for a field."""
    return PREFIX + name


def display_name(key):
    """Strip prefix from a field key for display."""
    if key.startswith(PREFIX):
        return key[len(PREFIX):]
    return key


def verb_key(field_key):
    """Get the verb settings key for a field."""
    return field_key + "_verb"


def get_app_path():
    """Get the app's directory path on the device."""
    if sys.implementation.name != "micropython":
        return "."
    try:
        apps = os.listdir("/apps")
        for a in apps:
            try:
                files = os.listdir("/apps/" + a)
                if "app.py" in files and "qr.py" in files:
                    return "/apps/" + a
            except OSError:
                pass
    except OSError:
        pass
    return "."


def generate_token():
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


def format_exception(e):
    """Format an exception with traceback."""
    import io
    buf = io.StringIO()
    sys.print_exception(e, buf)
    return buf.getvalue()


def url_decode(s):
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


def parse_form(body):
    """Parse URL-encoded form data."""
    data = {}
    if not body:
        return data
    for pair in body.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            data[url_decode(key)] = url_decode(value)
    return data


def html_esc(s):
    """Escape HTML special characters."""
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
