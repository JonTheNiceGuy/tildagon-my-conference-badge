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
EVENT_LOGO_FIELD = "__event_logo__"
KEY_EVENT_LOGO = PREFIX + "event_logo"
EVENT_IMAGES_DIR = "event_images"


def get_event_logos(app_path):
    """Return alphabetically sorted list of (display_name, filename) for event logos.

    Scans app_path/event_images/ for JPEG files. Display name is derived from
    the filename: extension stripped, hyphens/underscores replaced with spaces,
    then title-cased. e.g. "emfcamp-2024.jpg" -> "Emfcamp 2024".
    """
    logos_dir = app_path + "/" + EVENT_IMAGES_DIR
    try:
        files = sorted(os.listdir(logos_dir))
    except OSError:
        return []
    result = []
    for f in files:
        if f.lower().endswith(".jpg") or f.lower().endswith(".jpeg"):
            name = f.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
            result.append((name, f))
    return result

# =============================================================================
# Full 140 HTML/CSS Named Colours (using floats 0.0-1.0 for ctx.rgb/rgba)
# Grouped by category for easier selection in web UI
# =============================================================================

# Pink colours
COLOURS_PINK = {
    "pink": (1.0, 0.753, 0.796),
    "lightpink": (1.0, 0.714, 0.757),
    "hotpink": (1.0, 0.412, 0.706),
    "deeppink": (1.0, 0.078, 0.576),
    "palevioletred": (0.859, 0.439, 0.576),
    "mediumvioletred": (0.780, 0.082, 0.522),
}

# Purple colours
COLOURS_PURPLE = {
    "lavender": (0.902, 0.902, 0.980),
    "thistle": (0.847, 0.749, 0.847),
    "plum": (0.867, 0.627, 0.867),
    "orchid": (0.855, 0.439, 0.839),
    "violet": (0.933, 0.510, 0.933),
    "fuchsia": (1.0, 0.0, 1.0),
    "magenta": (1.0, 0.0, 1.0),
    "mediumorchid": (0.729, 0.333, 0.827),
    "darkorchid": (0.6, 0.196, 0.8),
    "darkviolet": (0.580, 0.0, 0.827),
    "blueviolet": (0.541, 0.169, 0.886),
    "darkmagenta": (0.545, 0.0, 0.545),
    "purple": (0.502, 0.0, 0.502),
    "mediumpurple": (0.576, 0.439, 0.859),
    "mediumslateblue": (0.482, 0.408, 0.933),
    "slateblue": (0.416, 0.353, 0.804),
    "darkslateblue": (0.282, 0.239, 0.545),
    "rebeccapurple": (0.4, 0.2, 0.6),
    "indigo": (0.294, 0.0, 0.510),
}

# Red colours
COLOURS_RED = {
    "lightsalmon": (1.0, 0.627, 0.478),
    "salmon": (0.980, 0.502, 0.447),
    "darksalmon": (0.914, 0.588, 0.478),
    "lightcoral": (0.941, 0.502, 0.502),
    "indianred": (0.804, 0.361, 0.361),
    "crimson": (0.863, 0.078, 0.235),
    "red": (1.0, 0.0, 0.0),
    "firebrick": (0.698, 0.133, 0.133),
    "darkred": (0.545, 0.0, 0.0),
}

# Orange colours
COLOURS_ORANGE = {
    "orange": (1.0, 0.647, 0.0),
    "darkorange": (1.0, 0.549, 0.0),
    "coral": (1.0, 0.498, 0.314),
    "tomato": (1.0, 0.388, 0.278),
    "orangered": (1.0, 0.271, 0.0),
}

# Yellow colours
COLOURS_YELLOW = {
    "gold": (1.0, 0.843, 0.0),
    "yellow": (1.0, 1.0, 0.0),
    "lightyellow": (1.0, 1.0, 0.878),
    "lemonchiffon": (1.0, 0.980, 0.804),
    "lightgoldenrodyellow": (0.980, 0.980, 0.824),
    "papayawhip": (1.0, 0.937, 0.835),
    "moccasin": (1.0, 0.894, 0.710),
    "peachpuff": (1.0, 0.855, 0.725),
    "palegoldenrod": (0.933, 0.910, 0.667),
    "khaki": (0.941, 0.902, 0.549),
    "darkkhaki": (0.741, 0.718, 0.420),
}

# Green colours
COLOURS_GREEN = {
    "greenyellow": (0.678, 1.0, 0.184),
    "chartreuse": (0.498, 1.0, 0.0),
    "lawngreen": (0.486, 0.988, 0.0),
    "lime": (0.0, 1.0, 0.0),
    "limegreen": (0.196, 0.804, 0.196),
    "palegreen": (0.596, 0.984, 0.596),
    "lightgreen": (0.565, 0.933, 0.565),
    "mediumspringgreen": (0.0, 0.980, 0.604),
    "springgreen": (0.0, 1.0, 0.498),
    "mediumseagreen": (0.235, 0.702, 0.443),
    "seagreen": (0.180, 0.545, 0.341),
    "forestgreen": (0.133, 0.545, 0.133),
    "green": (0.0, 0.502, 0.0),
    "darkgreen": (0.0, 0.392, 0.0),
    "yellowgreen": (0.604, 0.804, 0.196),
    "olivedrab": (0.420, 0.557, 0.137),
    "darkolivegreen": (0.333, 0.420, 0.184),
    "mediumaquamarine": (0.4, 0.804, 0.667),
    "darkseagreen": (0.561, 0.737, 0.561),
    "lightseagreen": (0.125, 0.698, 0.667),
    "darkcyan": (0.0, 0.545, 0.545),
    "teal": (0.0, 0.502, 0.502),
}

# Cyan colours
COLOURS_CYAN = {
    "aqua": (0.0, 1.0, 1.0),
    "cyan": (0.0, 1.0, 1.0),
    "lightcyan": (0.878, 1.0, 1.0),
    "paleturquoise": (0.686, 0.933, 0.933),
    "aquamarine": (0.498, 1.0, 0.831),
    "turquoise": (0.251, 0.878, 0.816),
    "mediumturquoise": (0.282, 0.820, 0.800),
    "darkturquoise": (0.0, 0.808, 0.820),
}

# Blue colours
COLOURS_BLUE = {
    "cadetblue": (0.373, 0.620, 0.627),
    "steelblue": (0.275, 0.510, 0.706),
    "lightsteelblue": (0.690, 0.769, 0.871),
    "lightblue": (0.678, 0.847, 0.902),
    "powderblue": (0.690, 0.878, 0.902),
    "lightskyblue": (0.529, 0.808, 0.980),
    "skyblue": (0.529, 0.808, 0.922),
    "cornflowerblue": (0.392, 0.584, 0.929),
    "deepskyblue": (0.0, 0.749, 1.0),
    "dodgerblue": (0.118, 0.565, 1.0),
    "royalblue": (0.255, 0.412, 0.882),
    "blue": (0.0, 0.0, 1.0),
    "mediumblue": (0.0, 0.0, 0.804),
    "darkblue": (0.0, 0.0, 0.545),
    "navy": (0.0, 0.0, 0.502),
    "midnightblue": (0.098, 0.098, 0.439),
}

# Brown colours
COLOURS_BROWN = {
    "cornsilk": (1.0, 0.973, 0.863),
    "blanchedalmond": (1.0, 0.922, 0.804),
    "bisque": (1.0, 0.894, 0.769),
    "navajowhite": (1.0, 0.871, 0.678),
    "wheat": (0.961, 0.871, 0.702),
    "burlywood": (0.871, 0.722, 0.529),
    "tan": (0.824, 0.706, 0.549),
    "rosybrown": (0.737, 0.561, 0.561),
    "sandybrown": (0.957, 0.643, 0.376),
    "goldenrod": (0.855, 0.647, 0.125),
    "darkgoldenrod": (0.722, 0.525, 0.043),
    "peru": (0.804, 0.522, 0.247),
    "chocolate": (0.824, 0.412, 0.118),
    "olive": (0.502, 0.502, 0.0),
    "saddlebrown": (0.545, 0.271, 0.075),
    "sienna": (0.627, 0.322, 0.176),
    "brown": (0.647, 0.165, 0.165),
    "maroon": (0.502, 0.0, 0.0),
}

# White colours
COLOURS_WHITE = {
    "white": (1.0, 1.0, 1.0),
    "snow": (1.0, 0.980, 0.980),
    "honeydew": (0.941, 1.0, 0.941),
    "mintcream": (0.961, 1.0, 0.980),
    "azure": (0.941, 1.0, 1.0),
    "aliceblue": (0.941, 0.973, 1.0),
    "ghostwhite": (0.973, 0.973, 1.0),
    "whitesmoke": (0.961, 0.961, 0.961),
    "seashell": (1.0, 0.961, 0.933),
    "beige": (0.961, 0.961, 0.863),
    "oldlace": (0.992, 0.961, 0.902),
    "floralwhite": (1.0, 0.980, 0.941),
    "ivory": (1.0, 1.0, 0.941),
    "antiquewhite": (0.980, 0.922, 0.843),
    "linen": (0.980, 0.941, 0.902),
    "lavenderblush": (1.0, 0.941, 0.961),
    "mistyrose": (1.0, 0.894, 0.882),
}

# Grey colours
COLOURS_GREY = {
    "gainsboro": (0.863, 0.863, 0.863),
    "lightgray": (0.827, 0.827, 0.827),
    "silver": (0.753, 0.753, 0.753),
    "darkgray": (0.663, 0.663, 0.663),
    "dimgray": (0.412, 0.412, 0.412),
    "gray": (0.502, 0.502, 0.502),
    "lightslategray": (0.467, 0.533, 0.600),
    "slategray": (0.439, 0.502, 0.565),
    "darkslategray": (0.184, 0.310, 0.310),
    "black": (0.0, 0.0, 0.0),
}

# Combined dictionary of all colours
COLOURS = {}
COLOURS.update(COLOURS_PINK)
COLOURS.update(COLOURS_PURPLE)
COLOURS.update(COLOURS_RED)
COLOURS.update(COLOURS_ORANGE)
COLOURS.update(COLOURS_YELLOW)
COLOURS.update(COLOURS_GREEN)
COLOURS.update(COLOURS_CYAN)
COLOURS.update(COLOURS_BLUE)
COLOURS.update(COLOURS_BROWN)
COLOURS.update(COLOURS_WHITE)
COLOURS.update(COLOURS_GREY)

COLOUR_NAMES = list(COLOURS.keys())

# Colour groups for web UI dropdown organization
COLOUR_GROUPS = [
    ("Pink", list(COLOURS_PINK.keys())),
    ("Purple", list(COLOURS_PURPLE.keys())),
    ("Red", list(COLOURS_RED.keys())),
    ("Orange", list(COLOURS_ORANGE.keys())),
    ("Yellow", list(COLOURS_YELLOW.keys())),
    ("Green", list(COLOURS_GREEN.keys())),
    ("Cyan", list(COLOURS_CYAN.keys())),
    ("Blue", list(COLOURS_BLUE.keys())),
    ("Brown", list(COLOURS_BROWN.keys())),
    ("White", list(COLOURS_WHITE.keys())),
    ("Grey", list(COLOURS_GREY.keys())),
]

# Default indicator colours (foreground over background)
# Light grey foreground, dark grey background
INDICATOR_DEFAULTS = {
    "foreground": "lightgray",  # Incomplete segments
    "background": "darkgray",   # Complete segments (progress fill)
}


def get_indicator_defaults():
    """Get default indicator colours as RGB tuples."""
    fg = COLOURS.get(INDICATOR_DEFAULTS["foreground"], (0.827, 0.827, 0.827))
    bg = COLOURS.get(INDICATOR_DEFAULTS["background"], (0.663, 0.663, 0.663))
    return (fg, bg)


def colour_rgb(name, default=None):
    """Get RGB tuple (floats 0.0-1.0) for a colour name, with fallback."""
    if name and name.lower() in COLOURS:
        return COLOURS[name.lower()]
    if default is not None:
        return default
    return (0.5, 0.5, 0.5)  # Medium grey fallback


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
        path = __file__
        if "/" in path:
            dir_path = path.rsplit("/", 1)[0]
            if not dir_path.startswith("/"):
                dir_path = "/" + dir_path
            return dir_path
    except NameError:
        pass
    return "."


def generate_token():
    """Generate a 4-character human-friendly session token.

    Uses a 30-character set excluding ambiguous characters (0/O, 1/l/I).
    Provides ~19.6 bits of entropy (810,000 combinations).
    """
    # Excludes: 0, 1, i, l, o (ambiguous with O, I, l, 0)
    chars = "23456789abcdefghjkmnpqrstuvwxyz"
    try:
        raw = os.urandom(4)
        token = ""
        for b in raw:
            token += chars[b % len(chars)]
        return token
    except Exception:
        import random
        token = ""
        for _ in range(4):
            token += chars[random.randint(0, len(chars) - 1)]
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
