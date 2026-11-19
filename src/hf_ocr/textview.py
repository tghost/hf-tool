"""Paged text viewer for the 320x170 panel.

The screen is tiny, so the recognized text is split into pages of wrapped
lines and navigated with the keypad's numeric row and arrow keys.
"""

import unicodedata

PAGE_ROWS = 7
LINE_H = 16
HEADER_H = 18
FOOTER_H = 14


def _display_width(text):
    """Width in half-width cells; CJK glyphs take two cells."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def wrap(text, columns=38):
    """Wrap text to the panel width, honouring CJK double-width glyphs."""
    lines = []
    for raw in text.split("\n"):
        if not raw.strip():
            lines.append("")
            continue
        cur = ""
        cur_w = 0
        for ch in raw:
            w = _display_width(ch)
            if cur_w + w > columns and cur:
                lines.append(cur)
                cur = ""
                cur_w = 0
            cur += ch
            cur_w += w
        if cur:
            lines.append(cur)
    return lines or [""]


class TextViewer:
    """Owns pagination state and renders the text onto a Display."""

    def __init__(self, display, columns=38, rows=PAGE_ROWS):
        self.display = display
        self.columns = columns
        self.rows = rows
        self.lines = [""]
        self.page = 0

    @property
    def page_count(self):
        return max(1, (len(self.lines) + self.rows - 1) // self.rows)

    def set_text(self, text):
        self.lines = wrap(text, self.columns)
        self.page = 0

    def next_page(self):
        self.page = (self.page + 1) % self.page_count

    def prev_page(self):
        self.page = (self.page - 1) % self.page_count

    def render(self, title="", status=""):
        d = self.display
        d.clear()
        # Header
        d.rect((0, 0, d.width, HEADER_H), fill=(24, 28, 38))
        d.text((4, 3), title[:26], size=12, color=(72, 198, 255), bold=True)
        d.line((0, HEADER_H, d.width, HEADER_H), color=(48, 56, 72))

        # Body
        y = HEADER_H + 2
        start = self.page * self.rows
        chunk = self.lines[start:start + self.rows]
        for i, ln in enumerate(chunk):
            color = (226, 232, 242) if ln.strip() else (60, 66, 80)
            d.text((4, y + i * LINE_H), ln[: self.columns], size=12, color=color)

        # Footer
        fy = d.height - FOOTER_H
        d.rect((0, fy, d.width, d.height), fill=(24, 28, 38))
        d.line((0, fy, d.width, fy), color=(48, 56, 72))
        d.text((4, fy + 1), status or "←/→ 翻页", size=10, color=(150, 160, 180))
        right = "%d/%d" % (self.page + 1, self.page_count)
        d.text((d.width - d.text_width(right, 10) - 4, fy + 1), right,
               size=10, color=(150, 160, 180))
        d.flush()
