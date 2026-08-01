"""Conference Badge app - main application class."""

import math
import time
import os

import app
import settings
from app_components import clear_background
from events.input import BUTTON_TYPES, Buttons

from .helpers import (
    KEY_DISPLAY_FIELDS, KEY_NAME, KEY_HAS_STARTED,
    KEY_ICE_PHONE, KEY_ICE_NAME, KEY_ICE_NOTES, KEY_BATTERY_ENABLED,
    IMAGE_FILENAME, IMAGE_FIELD, EVENT_LOGO_FIELD,
    KEY_EVENT_LOGO, EVENT_IMAGES_DIR, get_event_logos, default_event_logo,
    colour_rgb, display_name, verb_key, get_app_path,
    get_indicator_defaults
)
from .web import WebServerMixin
from .page_indicator import draw_page_indicator

# Set to True to print verbose image/render diagnostics over the mpremote serial
# console. Leave False for normal use.
DEBUG = False


def _dbg(*parts):
    if DEBUG:
        print("[conbadge] " + " ".join(str(p) for p in parts))


class ConferenceBadge(app.App, WebServerMixin):
    """Multi-page conference badge with ICE support and web configuration."""

    DISPLAY_RADIUS = 120
    AUTO_CYCLE_MS = 5000
    ICE_CONFIRM_TIMEOUT_MS = 5000
    CONFIG_CONFIRM_TIMEOUT_MS = 5000

    FONT_SIZES = [56, 48, 40, 32, 24]
    MIN_FONT_SIZE = 24

    # Default colours (floats 0.0-1.0 for ctx.rgb)
    bg_color = (0.0, 0.0, 0.0)
    fg_color = (1.0, 1.0, 1.0)
    header_bg_color = (1.0, 0.0, 0.0)
    header_fg_color = (1.0, 1.0, 1.0)
    ice_bg_color = (1.0, 0.0, 0.0)
    ice_fg_color = (1.0, 1.0, 1.0)  # was black on red - poor contrast in the field

    # App modes
    MODE_SPLASH = 0
    MODE_BADGE = 1
    MODE_WEB_PROMPT = 2
    MODE_WEB_SERVER = 3
    MODE_WIFI_ERROR = 4
    MODE_CONFIG_MENU = 5

    SPLASH_DURATION_MS = 10000
    WIFI_ERROR_DURATION_MS = 2000

    # power.BatteryLevel() does a real I2C read - re-sample it this often
    # rather than on every render frame.
    BATTERY_REFRESH_MS = 30000

    # Developer shortcut: tap A (UP) this many times, each within this
    # window of the last, to pull the latest app code from GitHub and
    # reboot - avoids needing REPL/serial access to redeploy while testing.
    DEV_TAP_COUNT = 4
    DEV_TAP_WINDOW_MS = 800
    DEV_DEPLOY_URL = "https://raw.githubusercontent.com/JonTheNiceGuy/tildagon-my-conference-badge/relay-config/deploy_device.py"
    # Half-width (degrees) of the feedback arc shown after tap 1, 2, 3 -
    # centred on button A/top (11:45-12:15, 11:30-12:30, 11:15-12:45), so
    # each registered press is immediately visible without waiting for
    # the 4th to find out whether presses are being detected at all.
    DEV_TAP_ARC_HALF_WIDTHS_DEG = [7.5, 15, 22.5]

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

        # WiFi error state
        self.wifi_error_timer = 0

        # Web server state
        self.mode = self.MODE_SPLASH
        self.server_backend = None  # "local" or "relay" while MODE_WEB_SERVER is active
        self.server_socket = None  # local backend only
        self.session_id = ""  # relay backend only
        self.relay_confirm_code = ""  # relay backend only - "code B" of the 2FA manual-entry flow
        self.local_code = ""  # local backend only
        self.local_failed_attempts = 0
        self.active_token = ""  # whichever of the above is in use, for URL building
        self.display_host = ""
        self.display_code = ""
        self.server_url = ""
        self.qr_matrix = None
        self.ble_soon_flash_timer = 0
        self.start_error = ""

        # Battery indicator state (badge pages only) - cached, see
        # _get_battery_level and BATTERY_REFRESH_MS
        self.battery_level = None
        self.battery_checked_at = 0

        # Developer redeploy-shortcut state - see _update_dev_shortcut
        self._dev_tap_count = 0
        self._dev_tap_last_ms = 0
        self._dev_up_was_down = False
        self._dev_redeploying = False

        # Image state
        self.app_path = get_app_path()
        self.image_path = self.app_path + "/" + IMAGE_FILENAME
        self.event_logo_path = None  # set in _load_settings

        # Settings are reloaded only when the web server marks them dirty,
        # not every frame (see update() and WebServerMixin._persist_settings).
        self._settings_dirty = False
        self._load_settings()

    # --- Settings ---

    def _load_settings(self):
        """Load display fields and values from settings."""
        # First-run migration: import system "name" if available
        if not settings.get(KEY_HAS_STARTED):
            settings.set(KEY_HAS_STARTED, 1)
            system_name = settings.get("name")
            if system_name:
                settings.set(KEY_NAME, [system_name])
            settings.save()

        self.display_fields = settings.get(KEY_DISPLAY_FIELDS)
        if self.display_fields is None:
            self.display_fields = [EVENT_LOGO_FIELD, KEY_NAME]
            settings.set(KEY_DISPLAY_FIELDS, self.display_fields)

        self.ice_phone = settings.get(KEY_ICE_PHONE)
        self.ice_name = settings.get(KEY_ICE_NAME)
        self.ice_notes = settings.get(KEY_ICE_NOTES)

        # Battery indicator defaults to on; stored as 0 when explicitly
        # disabled via the web UI, absent/truthy otherwise.
        self.battery_enabled = settings.get(KEY_BATTERY_ENABLED) != 0

        # Load selected event logo
        event_logos = get_event_logos(self.app_path)
        valid_filenames = [f for _, f in event_logos]
        selected_logo = settings.get(KEY_EVENT_LOGO)
        if selected_logo not in valid_filenames:
            selected_logo = default_event_logo(event_logos)
        if selected_logo:
            self.event_logo_path = self.app_path + "/" + EVENT_IMAGES_DIR + "/" + selected_logo
        else:
            self.event_logo_path = None
        _dbg("load_settings app_path=", self.app_path,
             "logos=", valid_filenames,
             "selected=", repr(selected_logo),
             "event_logo_path=", repr(self.event_logo_path))

        # Cache image existence check
        try:
            os.stat(self.image_path)
            self._image_exists = True
        except (OSError, AttributeError):
            self._image_exists = False

    def _has_settings(self):
        """Check if any meaningful settings are configured."""
        for field in self.display_fields:
            if field == IMAGE_FIELD or field == EVENT_LOGO_FIELD:
                continue
            val = settings.get(field)
            if val:
                return True
        return False

    def _has_ice_configured(self):
        return self.ice_phone or self.ice_name

    def _has_image(self):
        return self._image_exists

    def _total_pages(self):
        """Total number of pages."""
        return max(len(self.display_fields), 1) if self.display_fields else 1

    def _get_field_value(self, field_key):
        return settings.get(field_key)

    def _get_field_label(self, field_key):
        return display_name(field_key)

    def _get_field_verb(self, field_key):
        verb = settings.get(verb_key(field_key))
        if verb:
            return verb
        return "is"

    # --- Text Fitting ---

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

    # --- Main Loop ---

    async def run(self, render_update):
        self._last_tick_time = time.ticks_ms()
        while True:
            if self.mode == self.MODE_WEB_SERVER and not self.button_states.get(BUTTON_TYPES["CANCEL"]):
                # Skip starting another poll if cancel is already pressed -
                # otherwise a press observed right here would still have to
                # wait out one more full poll cycle before update() gets to
                # act on it. _poll_server() itself keeps rendering/checking
                # buttons via _render_tick while any network call it makes
                # is in flight (see web.py) - it isn't a blocking pause.
                await self._poll_server(render_update)

            await self._render_tick(render_update)

    async def _render_tick(self, render_update):
        """One frame: advance timers/state and render. Called once per
        run() loop iteration, and also (repeatedly, ~every 0.1s) as the
        periodic callback while a relay network call runs on a background
        thread, so the badge doesn't visibly freeze while waiting on it.
        """
        cur_time = time.ticks_ms()
        delta = time.ticks_diff(cur_time, self._last_tick_time)
        self._last_tick_time = cur_time
        self.update(delta)
        await render_update()

    def update(self, delta):
        self._update_dev_shortcut()

        if self._settings_dirty:
            self._settings_dirty = False
            self._load_settings()

        if self.mode == self.MODE_SPLASH:
            self._update_splash(delta)
        elif self.mode == self.MODE_BADGE:
            self._update_badge(delta)
        elif self.mode == self.MODE_WEB_PROMPT:
            self._update_web_prompt()
        elif self.mode == self.MODE_CONFIG_MENU:
            self._update_config_menu(delta)
        elif self.mode == self.MODE_WEB_SERVER:
            self._update_web_server()
        elif self.mode == self.MODE_WIFI_ERROR:
            self._update_wifi_error(delta)

    def _update_dev_shortcut(self):
        """Tap A (UP) DEV_TAP_COUNT times quickly: pull the latest app
        code from GitHub and reboot. Edge-triggered (only counts the
        press, not every frame it's held) via _dev_up_was_down.

        The actual fetch is deferred to the *next* update() cycle after
        the 4th tap, rather than run immediately here - _dev_redeploying
        gets one full draw() first (see draw()'s early branch), so there's
        an on-screen "please wait" cue before the blocking network call
        freezes rendering, instead of the badge just appearing to hang.
        """
        if self._dev_redeploying:
            self._trigger_dev_redeploy()
            return

        up_down = self.button_states.get(BUTTON_TYPES["UP"])
        if up_down and not self._dev_up_was_down:
            now = time.ticks_ms()
            if self._dev_tap_count > 0 and time.ticks_diff(now, self._dev_tap_last_ms) > self.DEV_TAP_WINDOW_MS:
                self._dev_tap_count = 0
            self._dev_tap_count += 1
            self._dev_tap_last_ms = now
            print("Dev shortcut: tap " + str(self._dev_tap_count) + "/" + str(self.DEV_TAP_COUNT))
            if self._dev_tap_count >= self.DEV_TAP_COUNT:
                self._dev_tap_count = 0
                self._dev_redeploying = True
        self._dev_up_was_down = up_down

    def _trigger_dev_redeploy(self):
        """Pull the latest app code from GitHub and reboot. Blocking (this
        is a one-shot developer action, not something in a per-frame
        loop) - the screen will appear to freeze for a few seconds while
        it downloads, then the badge resets. On failure, falls back to
        the existing WiFi-error screen (with the real exception message)
        instead of failing silently to a console you might not have open.
        """
        print("Dev shortcut: redeploying from " + self.DEV_DEPLOY_URL)
        try:
            import requests
            exec(requests.get(self.DEV_DEPLOY_URL).text)
        except Exception as e:
            print("Dev redeploy failed: " + str(e))
            self._dev_redeploying = False
            self.start_error = "Redeploy failed: " + str(e)
            self.mode = self.MODE_WIFI_ERROR
            self.wifi_error_timer = 0
            return
        import machine
        machine.reset()

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
                self.mode = self.MODE_CONFIG_MENU
            elif self.ice_screen == 0:
                self._prev_page()
                self.page_timer = 0
            self.button_states.clear()

        # Right (B) - ICE mode / navigation
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            if self.ice_screen == 0 and not self.ice_confirm_mode and not self.config_confirm_mode:
                self.ice_confirm_mode = True
                self.ice_confirm_timer = 0
            elif self.ice_screen == 1:
                self.ice_screen = 2  # Contact -> Notes
            elif self.ice_screen == 2:
                self.ice_screen = 1  # Notes -> Contact (back)
            self.button_states.clear()

        # Down (D) - Config mode
        if self.button_states.get(BUTTON_TYPES["DOWN"]):
            if self.ice_screen == 0 and not self.ice_confirm_mode and not self.config_confirm_mode:
                self.config_confirm_mode = True
                self.config_confirm_timer = 0
            self.button_states.clear()

    def _update_web_prompt(self):
        """Update web server prompt mode."""
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.button_states.clear()
            self.mode = self.MODE_CONFIG_MENU

        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.mode = self.MODE_BADGE

    def _update_config_menu(self, delta):
        """Update config method picker mode."""
        if self.ble_soon_flash_timer > 0:
            self.ble_soon_flash_timer = max(0, self.ble_soon_flash_timer - delta)

        if self.button_states.get(BUTTON_TYPES["UP"]):  # A - Local Network
            self.button_states.clear()
            if not self._start_local_server():
                self.mode = self.MODE_WIFI_ERROR
                self.wifi_error_timer = 0
        elif self.button_states.get(BUTTON_TYPES["RIGHT"]):  # B - Relay
            self.button_states.clear()
            if not self._start_relay_server():
                self.mode = self.MODE_WIFI_ERROR
                self.wifi_error_timer = 0
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):  # C - BLE (not yet implemented)
            self.button_states.clear()
            self.ble_soon_flash_timer = 1500
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.mode = self.MODE_BADGE

    def _update_web_server(self):
        """Update web server mode."""
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self._stop_web_server()

    def _update_wifi_error(self, delta):
        """Update WiFi error display mode."""
        self.wifi_error_timer += delta
        if self.wifi_error_timer >= self.WIFI_ERROR_DURATION_MS:
            self.wifi_error_timer = 0
            self.mode = self.MODE_WEB_PROMPT

    def _update_splash(self, delta):
        """Update splash screen mode."""
        self.splash_timer += delta

        if self.splash_timer >= self.SPLASH_DURATION_MS:
            self._end_splash()
            return

        # Buttons A-E skip splash (UP=A, RIGHT=B, CONFIRM=C, DOWN=D, LEFT=E)
        # F (CANCEL) does not skip
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]) or \
           self.button_states.get(BUTTON_TYPES["UP"]) or \
           self.button_states.get(BUTTON_TYPES["DOWN"]) or \
           self.button_states.get(BUTTON_TYPES["LEFT"]) or \
           self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.button_states.clear()
            self._end_splash()

    def _end_splash(self):
        """End splash screen and go to appropriate mode."""
        self.splash_timer = 0
        if not self._has_settings():
            self.mode = self.MODE_CONFIG_MENU
        else:
            self.mode = self.MODE_BADGE

    def _next_page(self):
        total = self._total_pages()
        if total > 0:
            self.current_page = (self.current_page + 1) % total

    def _prev_page(self):
        total = self._total_pages()
        if total > 0:
            self.current_page = (self.current_page - 1) % total

    # --- Drawing ---

    def draw(self, ctx):
        clear_background(ctx)
        ctx.text_align = ctx.CENTER
        ctx.font = "Arimo Bold"

        if self._dev_redeploying:
            self._draw_dev_redeploying(ctx)
        elif self.mode == self.MODE_SPLASH:
            self._draw_splash(ctx)
        elif self.mode == self.MODE_WEB_PROMPT:
            self._draw_web_prompt(ctx)
        elif self.mode == self.MODE_CONFIG_MENU:
            self._draw_config_menu(ctx)
        elif self.mode == self.MODE_WEB_SERVER:
            self._draw_web_server(ctx)
        elif self.mode == self.MODE_WIFI_ERROR:
            self._draw_wifi_error(ctx)
        elif self.ice_confirm_mode:
            self._draw_ice_confirm(ctx)
        elif self.config_confirm_mode:
            self._draw_config_confirm(ctx)
        elif self.ice_screen > 0:
            self._draw_ice_screen(ctx)
        else:
            self._draw_badge_page(ctx)

        self._draw_dev_tap_feedback(ctx)
        self.draw_overlays(ctx)

    def _draw_dev_tap_feedback(self, ctx):
        """Overlay a small arc near button A/top after each registered
        tap of the dev-redeploy sequence, widening toward the 4th -
        direct visual proof presses are being detected, regardless of
        whatever else is on screen."""
        if not (1 <= self._dev_tap_count <= len(self.DEV_TAP_ARC_HALF_WIDTHS_DEG)):
            return
        half = self.DEV_TAP_ARC_HALF_WIDTHS_DEG[self._dev_tap_count - 1]
        self._draw_edge_arc(ctx, -half, half, (1.0, 0.9, 0.0), line_width=4)

    def _draw_dev_redeploying(self, ctx):
        """Shown for one frame before the blocking redeploy fetch starts,
        so the dev-shortcut doesn't just look like the badge hung."""
        ctx.rgb(0.0, 0.0, 0.0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(1.0, 1.0, 1.0)
        ctx.font_size = 20
        ctx.move_to(0, -10).text("Redeploying...")
        ctx.font_size = 14
        ctx.rgb(0.7, 0.7, 0.7)
        ctx.move_to(0, 20).text("Please wait")

    def _draw_splash(self, ctx):
        """Draw splash screen with button instructions."""
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)

        ctx.font_size = 22
        ctx.move_to(0, -90).text("My")
        ctx.move_to(0, -68).text("Conference")
        ctx.move_to(0, -46).text("Badge")

        ctx.font_size = 18
        ctx.move_to(0, -20).text("Press B for ICE info")
        ctx.move_to(0, 5).text("Press D for config")
        ctx.font_size = 16
        ctx.rgb(200, 200, 200)
        ctx.move_to(0, 35).text("Then press E to confirm")

        remaining = (self.SPLASH_DURATION_MS - self.splash_timer) / 1000
        ctx.font_size = 16
        ctx.rgb(150, 150, 150)
        remaining_str = str(int(remaining) + 1)
        ctx.move_to(0, 70).text("Any button to skip")
        ctx.move_to(0, 95).text("(" + remaining_str + "s)")

    def _draw_web_prompt(self, ctx):
        """Draw web server start prompt."""
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)
        ctx.font_size = 24
        ctx.move_to(0, -40).text("Start Web Settings?")
        ctx.font_size = 20
        ctx.move_to(0, 0).text("Press B to choose")
        ctx.move_to(0, 30).text("Press F to cancel")
        ctx.rgb(150, 150, 150)
        ctx.font_size = 14
        ctx.move_to(0, 70).text("Requires WiFi connection")

    def _draw_config_menu(self, ctx):
        """Draw the config method picker (Local Network / Relay / BLE)."""
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)
        ctx.font_size = 20
        ctx.move_to(0, -70).text("Config Method")

        ctx.font_size = 18
        ctx.move_to(0, -25).text("A: Local Network")
        ctx.move_to(0, 5).text("B: Relay (Internet)")

        if self.ble_soon_flash_timer > 0:
            ctx.rgb(1.0, 0.78, 0.0)
            ctx.move_to(0, 35).text("C: BLE - coming soon!")
        else:
            ctx.rgb(0.47, 0.47, 0.47)
            ctx.move_to(0, 35).text("C: BLE (not yet)")

        ctx.rgb(0.59, 0.59, 0.59)
        ctx.font_size = 14
        ctx.move_to(0, 75).text("F to cancel")

    # Extra, smaller tiers tried only when a caller passes a lower
    # min_font_size - vertical space below the QR code is tight enough that
    # a single small line usually beats wrapping to two readable ones.
    FONT_SIZES_FINE = [56, 48, 40, 32, 24, 20, 18, 16]

    def _fit_token_lines(self, ctx, text, y_position, max_lines=2, min_font_size=None):
        """Fit a single unbroken token (no spaces, e.g. an IP:port or a
        code) to the circular screen: shrink font first, then break
        mid-string if it still doesn't fit even at the smallest size.

        Every caller draws with an increment-before-draw convention (see
        _draw_web_server/_draw_relay_confirm): y_position is where the
        baseline sits *before* this line's own font-height is added, so
        the real drawn baseline ends up at y_position+font_size, not at
        y_position itself. Checking width at y_position alone under-counts
        how much the circle has already narrowed by the actual draw point
        - e.g. "code: 76bf45" measuring a few px narrower than what's
        really available a font-height further down. So the width check
        has to use that same, larger y for each candidate font size.
        """
        min_font_size = min_font_size or self.MIN_FONT_SIZE
        for font_size in self.FONT_SIZES_FINE:
            if font_size < min_font_size:
                break
            max_width = self.get_usable_width(y_position + font_size) * 0.9
            if max_width <= 0:
                continue
            ctx.font_size = font_size
            if ctx.text_width(text) <= max_width:
                return font_size, [text]

        max_width = self.get_usable_width(y_position + min_font_size) * 0.9
        if max_width <= 0:
            max_width = 1
        ctx.font_size = min_font_size
        lines = []
        remaining = text
        while remaining and len(lines) < max_lines - 1:
            current = ""
            for ch in remaining:
                test = current + ch
                if not current or ctx.text_width(test) <= max_width:
                    current = test
                else:
                    break
            lines.append(current)
            remaining = remaining[len(current):]
        if remaining:
            # Last line gets everything left over, even if it overflows -
            # better visible-but-cramped than silently dropped.
            lines.append(remaining)
        return min_font_size, lines

    def _draw_web_server(self, ctx):
        """Draw web server screen with QR code."""
        if self.server_backend == "relay" and self.relay_confirm_code:
            self._draw_relay_confirm(ctx)
            return

        ctx.rgb(255, 255, 255).rectangle(-120, -120, 240, 240).fill()

        qr_bottom = 0
        if self.qr_matrix:
            qr_size = len(self.qr_matrix)
            pixel_size = min(160 // qr_size, 4)
            total_size = qr_size * pixel_size
            offset_x = -total_size // 2

            # Push the QR as far up as it can go: place its top edge so the
            # top-left/top-right corners sit exactly on the display circle
            # (x=+-total_size/2, solved for y on x^2+y^2=DISPLAY_RADIUS^2),
            # instead of a fixed guessed offset. Maximises the QR's headroom
            # and leaves the rest of the circle for text.
            half = total_size / 2
            if half < self.DISPLAY_RADIUS:
                offset_y = -math.sqrt(self.DISPLAY_RADIUS ** 2 - half ** 2)
            else:
                offset_y = -self.DISPLAY_RADIUS
            offset_y = int(offset_y)

            for r in range(qr_size):
                for c in range(qr_size):
                    if self.qr_matrix[r][c]:
                        x = offset_x + c * pixel_size
                        y = offset_y + r * pixel_size
                        ctx.rgb(0, 0, 0).rectangle(x, y, pixel_size, pixel_size).fill()

            qr_bottom = offset_y + total_size

        ctx.rgb(255, 0, 0)
        y = qr_bottom + 2  # small border between the QR and the text below it;
                            # text is baseline-anchored (glyphs extend upward
                            # from y), so every line below advances y by its
                            # own font size *before* drawing, not after -
                            # otherwise the first line's glyphs render above
                            # this point, back into the QR.

        # min_font_size=16 (below the class-wide MIN_FONT_SIZE of 24):
        # a long IP:port fitting on one small line beats it wrapping to
        # two readable ones and blowing the line budget below the QR.
        host_font, host_lines = self._fit_token_lines(ctx, self.display_host or "", y, min_font_size=16)
        ctx.font_size = host_font
        for line in host_lines:
            y += host_font
            ctx.move_to(0, y).text(line)

        code_text = "code: " + (self.display_code or "")
        code_font, code_lines = self._fit_token_lines(ctx, code_text, y + 2, min_font_size=16)
        ctx.font_size = code_font
        y += 2
        for line in code_lines:
            y += code_font
            ctx.move_to(0, y).text(line)

        ctx.rgb(0, 0, 0)
        ctx.font_size = 12
        y += 14
        ctx.move_to(0, y).text("F to stop server")

    def _draw_relay_confirm(self, ctx):
        """Draw the second-factor confirmation screen: someone entered code A
        at the relay, so show code B for them to type back in. Takes over
        from the normal QR screen while active since it's time-sensitive."""
        ctx.rgb(0.0, 0.15, 0.45).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(1.0, 1.0, 1.0)
        ctx.font_size = 16
        ctx.move_to(0, -60).text("Someone entered your code.")
        ctx.move_to(0, -40).text("Give them this one:")

        code_font, code_lines = self._fit_token_lines(ctx, self.relay_confirm_code, 0, max_lines=2)
        ctx.font_size = code_font
        y = 0
        for line in code_lines:
            y += code_font
            ctx.move_to(0, y).text(line)
            y += 4

        ctx.font_size = 14
        ctx.rgb(0.7, 0.85, 1.0)
        ctx.move_to(0, y + 20).text("F to stop server")

    def _draw_wifi_error(self, ctx):
        """Draw the config-start error screen."""
        ctx.rgb(100, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(255, 255, 255)
        message = self.start_error or "Couldn't start config server"
        font_size, lines = self.fit_text(ctx, message, -20)
        ctx.font_size = font_size
        y = -20 - (len(lines) - 1) * (font_size + 4) // 2
        for line in lines:
            ctx.move_to(0, y).text(line)
            y += font_size + 4
        ctx.font_size = 16
        ctx.move_to(0, y + 14).text("Returning...")

    def _get_field_colours(self, field_key):
        """Get per-field colours, falling back to defaults."""
        hbg = colour_rgb(settings.get(field_key + "_hbg"), self.header_bg_color)
        hfg = colour_rgb(settings.get(field_key + "_hfg"), self.header_fg_color)
        vbg = colour_rgb(settings.get(field_key + "_vbg"), self.bg_color)
        vfg = colour_rgb(settings.get(field_key + "_vfg"), self.fg_color)
        return hbg, hfg, vbg, vfg

    def _get_battery_level(self):
        """Cached battery percentage (0-100), or None if unavailable.

        power.BatteryLevel() does a real I2C read against the charger IC,
        so this only re-samples it every BATTERY_REFRESH_MS rather than on
        every render frame - the draw loop just reuses whatever was last
        read to work out the bar's length.
        """
        now = time.ticks_ms()
        if self.battery_level is None or time.ticks_diff(now, self.battery_checked_at) >= self.BATTERY_REFRESH_MS:
            self.battery_checked_at = now
            try:
                import power
                self.battery_level = max(0.0, min(100.0, power.BatteryLevel()))
            except Exception as e:
                _dbg("battery read failed:", e)
                # Leave self.battery_level as whatever it was (None, or a
                # still-reasonable stale reading) rather than erroring.
        return self.battery_level

    def _draw_battery_line(self, ctx, y, colour):
        """1px battery indicator: a horizontal line centred on x=0 that
        pulls in from both ends as charge drops, rather than a
        conventional left-aligned bar."""
        level = self._get_battery_level()
        if level is None:
            return
        max_half_width = self.get_usable_width(y) * 0.4
        half_width = max_half_width * (level / 100.0)
        if half_width < 1:
            return
        ctx.rgb(*colour).rectangle(-half_width, y, half_width * 2, 1).fill()

    def _draw_edge_arc(self, ctx, start_degrees, end_degrees, colour, line_width=2, radius=119):
        """Stroke an arc on the display's edge. 0deg is the top of the
        screen (12 o'clock, button A) and degrees increase clockwise
        matching the button layout - 60deg=button B (NE), 120deg=button C
        (SE), 180deg=button D (S), 240deg=button E (SW), 300deg=button F
        (NW).
        """
        start_angle = math.radians((270 + start_degrees) % 360)
        end_angle = math.radians((270 + end_degrees) % 360)
        sweep = end_angle - start_angle
        if sweep < 0:
            sweep += 2 * math.pi

        ctx.rgb(*colour)
        ctx.line_width = line_width
        points = 30
        prev_x, prev_y = None, None
        for p in range(points + 1):
            t = p / points
            angle = start_angle + t * sweep
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            if prev_x is not None:
                ctx.move_to(prev_x, prev_y)
                ctx.line_to(x, y)
                ctx.stroke()
            prev_x, prev_y = x, y

    def _draw_badge_page(self, ctx):
        """Draw a normal badge page."""
        total = self._total_pages()

        if not self.display_fields:
            ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
            self._draw_no_fields(ctx)
            return

        field_key = self.display_fields[self.current_page % len(self.display_fields)]
        _dbg("draw_badge_page page=", self.current_page, "field=", field_key)

        # Image pages (use default indicator colors for black background)
        if field_key == IMAGE_FIELD:
            self._draw_image_page(ctx, self.image_path)
            if total > 1:
                self._draw_page_indicator(ctx)  # Uses blue/white defaults
            return

        if field_key == EVENT_LOGO_FIELD:
            self._draw_image_page(ctx, self.event_logo_path)
            if total > 1:
                self._draw_page_indicator(ctx)  # Uses blue/white defaults
            return

        field_value = self._get_field_value(field_key)
        field_label = self._get_field_label(field_key)
        verb = self._get_field_verb(field_key)
        hbg, hfg, vbg, vfg = self._get_field_colours(field_key)

        # Get indicator colours (foreground/background) for this field
        default_fg, default_bg = get_indicator_defaults()
        ind_fg_name = settings.get(field_key + "_ind_fg")
        ind_bg_name = settings.get(field_key + "_ind_bg")
        ind_fg = colour_rgb(ind_fg_name, default_fg)
        ind_bg = colour_rgb(ind_bg_name, default_bg)

        ctx.rgb(*vbg).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(*hbg).rectangle(-120, -120, 240, 100).fill()

        # Header
        ctx.font_size = 56
        ctx.rgb(*hfg).move_to(0, -60).text("Hello")
        header_text = "my " + field_label + " " + verb
        header_w = self.get_usable_width(-30) * 0.9
        header_font = 16
        for fs in [28, 24, 20, 18, 16]:
            ctx.font_size = fs
            if ctx.text_width(header_text) <= header_w:
                header_font = fs
                break
        ctx.font_size = header_font
        ctx.rgb(*hfg).move_to(0, -30).text(header_text)

        # Value - may be a string or list of up to 2 lines
        lines = []
        if isinstance(field_value, list):
            for part in field_value:
                if part and part.strip():
                    lines.append(part.strip())
        elif field_value:
            lines.append(field_value.strip())

        if lines:
            all_lines = []
            min_font = self.FONT_SIZES[0]
            for part in lines:
                fs, wrapped = self.fit_text(ctx, part, 40)
                min_font = min(min_font, fs)
                all_lines.extend(wrapped)
            num_lines = len(all_lines)
            # Rough starting caps by line count - short individual parts
            # (e.g. "Jon" / "Spriggs") each fit fine alone at a huge font,
            # so this alone isn't enough; the loop below is what actually
            # guarantees the block doesn't creep up into the header band,
            # by checking real position rather than guessing at a cap.
            if num_lines == 2:
                min_font = min(min_font, 48)
            elif num_lines >= 3:
                min_font = min(min_font, 32)

            header_bottom = -20  # bottom edge of the red header rectangle
            top_margin = 12  # room for the battery divider line sitting right on header_bottom
            bottom_limit = 105
            while True:
                line_height = min_font * 1.05
                total_height = line_height * num_lines
                center_y = 40
                start_y = center_y - (total_height / 2) + (line_height / 2)
                ascent = min_font * 0.75  # approximate glyph-top-above-baseline
                first_line_top = start_y - ascent
                last_line_y = start_y + (num_lines - 1) * line_height
                if first_line_top >= header_bottom + top_margin and last_line_y <= bottom_limit:
                    break
                if min_font <= self.MIN_FONT_SIZE:
                    # Can't shrink further without becoming unreadable -
                    # push the block down instead, off-centre if it must be.
                    start_y = max(start_y, header_bottom + top_margin + ascent)
                    break
                min_font -= 4

            ctx.font_size = min_font
            ctx.rgb(*vfg)
            for i, line in enumerate(all_lines):
                y = start_y + (i * line_height)
                ctx.move_to(0, y).text(line)
        else:
            ctx.font_size = 20
            ctx.font = "Arimo Italic"
            ctx.rgb(*vfg).move_to(0, 40).text("Not set")
            ctx.move_to(0, 65).text("Press D for settings")

        # Defaults to the header block's own foreground colour (hfg - white
        # unless that field's header colour was customised); field_key +
        # "_batt_fg" is an explicit per-field override. Used for both the
        # battery line and the ICE-configured indicator arc below.
        batt_fg = colour_rgb(settings.get(field_key + "_batt_fg"), hfg)

        if self.battery_enabled:
            self._draw_battery_line(ctx, -20, batt_fg)

        if self._has_ice_configured():
            self._draw_edge_arc(ctx, 52.5, 67.5, batt_fg)

        if total > 1:
            self._draw_page_indicator(ctx, ind_fg, ind_bg)

    def _draw_image_page(self, ctx, image_path):
        """Draw an image page."""
        ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
        _dbg("draw_image_page path=", repr(image_path))
        if image_path is None:
            _dbg("  -> image_path is None, nothing to draw")
        else:
            try:
                st = os.stat(image_path)
                _dbg("  stat ok, size=", st[6], "bytes")
            except Exception as e:
                _dbg("  stat FAILED:", repr(e))
        try:
            _dbg("  calling ctx.image(...)")
            ctx.image(image_path, -120, -120, 240, 240)
            _dbg("  ctx.image returned OK")
        except Exception as e:
            _dbg("  ctx.image RAISED:", repr(e))
            print("Image error: " + str(e) + " (path: " + str(image_path) + ")")
            ctx.rgb(*self.fg_color)
            ctx.font_size = 20
            ctx.move_to(0, -10).text("Image error")
            ctx.font_size = 16
            ctx.move_to(0, 20).text("Press D to reconfigure")

    def _draw_no_fields(self, ctx):
        ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 20
        ctx.font = "Arimo Italic"
        ctx.rgb(*self.fg_color).move_to(0, -10).text("No fields configured")
        ctx.move_to(0, 20).text("Press D for settings")

    def _draw_page_indicator(self, ctx, fg_color=None, bg_color=None):
        """Draw semi-circular progress indicator at bottom of display."""
        progress = min(self.page_timer / self.AUTO_CYCLE_MS, 1.0)
        draw_page_indicator(
            ctx, self._total_pages(), self.current_page, progress,
            fg_color, bg_color
        )

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
        ctx.move_to(0, 10).text("E: confirm | F: cancel")
        remaining = (self.ICE_CONFIRM_TIMEOUT_MS - self.ice_confirm_timer) / 1000
        ctx.font_size = 20
        remaining_str = str(int(remaining) + 1) + "s"
        ctx.move_to(0, 50).text("(" + remaining_str + ")")

    def _draw_config_confirm(self, ctx):
        ctx.rgb(0.0, 0.0, 0.39).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(1.0, 1.0, 1.0)

        y = -40
        title_font, title_lines = self.fit_text(ctx, "Enter Config Mode?", y)
        ctx.font_size = title_font
        for line in title_lines:
            ctx.move_to(0, y).text(line)
            y += title_font + 4

        y += 20
        prompt_font, prompt_lines = self.fit_text(ctx, "E: confirm | F: cancel", y)
        ctx.font_size = prompt_font
        for line in prompt_lines:
            ctx.move_to(0, y).text(line)
            y += prompt_font + 4

        remaining = (self.CONFIG_CONFIRM_TIMEOUT_MS - self.config_confirm_timer) / 1000
        ctx.font_size = 20
        remaining_str = str(int(remaining) + 1) + "s"
        ctx.move_to(0, y + 20).text("(" + remaining_str + ")")

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
            ctx.move_to(0, 90).text("B: back | F: exit")


__app_export__ = ConferenceBadge
