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
    KEY_ICE_PHONE, KEY_ICE_NAME, KEY_ICE_NOTES,
    IMAGE_FILENAME, IMAGE_FIELD, EMF_LOGO_FILENAME, EMF_LOGO_FIELD,
    colour_rgb, display_name, verb_key, get_app_path
)
from .web import WebServerMixin


class ConferenceBadge(app.App, WebServerMixin):
    """Multi-page conference badge with ICE support and web configuration."""

    DISPLAY_RADIUS = 120
    AUTO_CYCLE_MS = 5000
    ICE_CONFIRM_TIMEOUT_MS = 5000
    CONFIG_CONFIRM_TIMEOUT_MS = 5000

    FONT_SIZES = [56, 48, 40, 32, 24]
    MIN_FONT_SIZE = 24

    # Default colours
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

    SPLASH_DURATION_MS = 10000

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

        # Image state
        self.app_path = get_app_path()
        self.image_path = self.app_path + "/" + IMAGE_FILENAME
        self.emf_logo_path = self.app_path + "/" + EMF_LOGO_FILENAME

        # Load settings
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
            self.display_fields = [EMF_LOGO_FIELD, KEY_NAME]
            settings.set(KEY_DISPLAY_FIELDS, self.display_fields)

        self.ice_phone = settings.get(KEY_ICE_PHONE)
        self.ice_name = settings.get(KEY_ICE_NAME)
        self.ice_notes = settings.get(KEY_ICE_NOTES)

        # Cache image existence check
        try:
            os.stat(self.image_path)
            self._image_exists = True
        except (OSError, AttributeError):
            self._image_exists = False

    def _has_settings(self):
        """Check if any meaningful settings are configured."""
        for field in self.display_fields:
            if field == IMAGE_FIELD or field == EMF_LOGO_FIELD:
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
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.button_states.clear()
            if not self._start_web_server():
                pass

        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.mode = self.MODE_BADGE

    def _update_web_server(self):
        """Update web server mode."""
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self._stop_web_server()

    def _update_splash(self, delta):
        """Update splash screen mode."""
        self.splash_timer += delta

        if self.splash_timer >= self.SPLASH_DURATION_MS:
            self._end_splash()
            return

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
        if not self._has_settings():
            self.mode = self.MODE_WEB_PROMPT
            if self._start_web_server():
                pass
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
        remaining_str = str(int(remaining))
        ctx.move_to(0, 70).text("Starting soon...")
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

        ctx.rgb(255, 0, 0)
        font_size, _ = self.fit_text(ctx, self.server_url, qr_bottom)
        ctx.font_size = min(font_size, 16)
        ctx.move_to(0, qr_bottom).text(self.server_url)

        ctx.font_size = 16
        ctx.move_to(0, qr_bottom + 20).text("F to stop server")

    def _get_field_colours(self, field_key):
        """Get per-field colours, falling back to defaults."""
        hbg = colour_rgb(settings.get(field_key + "_hbg"), self.header_bg_color)
        hfg = colour_rgb(settings.get(field_key + "_hfg"), self.header_fg_color)
        vbg = colour_rgb(settings.get(field_key + "_vbg"), self.bg_color)
        vfg = colour_rgb(settings.get(field_key + "_vfg"), self.fg_color)
        return hbg, hfg, vbg, vfg

    def _draw_badge_page(self, ctx):
        """Draw a normal badge page."""
        total = self._total_pages()

        if not self.display_fields:
            ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
            self._draw_no_fields(ctx)
            return

        field_key = self.display_fields[self.current_page % len(self.display_fields)]

        # Image pages
        if field_key == IMAGE_FIELD:
            self._draw_image_page(ctx, self.image_path)
            if total > 1:
                self._draw_page_indicator(ctx, self.fg_color)
            return

        if field_key == EMF_LOGO_FIELD:
            self._draw_image_page(ctx, self.emf_logo_path)
            if total > 1:
                self._draw_page_indicator(ctx, self.fg_color)
            return

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
            # Cap font size based on line count to prevent overflow into header
            num_lines = len(all_lines)
            if num_lines == 2:
                min_font = min(min_font, 48)
            elif num_lines >= 3:
                min_font = min(min_font, 32)
            ctx.font_size = min_font
            ctx.rgb(*vfg)
            line_height = min_font * 1.05
            total_height = line_height * num_lines
            center_y = 40
            start_y = center_y - (total_height / 2) + (line_height / 2)
            for i, line in enumerate(all_lines):
                y = start_y + (i * line_height)
                ctx.move_to(0, y).text(line)
        else:
            ctx.font_size = 20
            ctx.font = "Arimo Italic"
            ctx.rgb(*vfg).move_to(0, 40).text("Not set")
            ctx.move_to(0, 65).text("Press D for settings")

        if total > 1:
            self._draw_page_indicator(ctx, vfg)

    def _draw_image_page(self, ctx, image_path):
        """Draw an image page."""
        ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
        try:
            ctx.image(image_path, -120, -120, 240, 240)
        except Exception:
            ctx.rgb(*self.fg_color)
            ctx.font_size = 20
            ctx.move_to(0, 0).text("Image error")

    def _draw_no_fields(self, ctx):
        ctx.rgb(*self.bg_color).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 20
        ctx.font = "Arimo Italic"
        ctx.rgb(*self.fg_color).move_to(0, -10).text("No fields configured")
        ctx.move_to(0, 20).text("Press D for settings")

    def _draw_page_indicator(self, ctx, active_color):
        num_pages = self._total_pages()
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
