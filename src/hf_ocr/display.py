"""Direct framebuffer renderer for the CardputerZero 320x170 panel.

The device exposes /dev/fb0 as RGB565 with a 640-byte stride. We mmap it and
push whole frames from Pillow, which keeps the drawing code simple and avoids
pulling a UI toolkit into a 352 MiB device.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FB_DEVICE = "/dev/fb0"
FB_WIDTH = 320
FB_HEIGHT = 170
FB_STRIDE = FB_WIDTH * 2

FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG = (14, 16, 22)
FG = (226, 232, 242)
MUTED = (128, 138, 158)
ACCENT = (72, 198, 255)
OK = (96, 220, 140)
WARN = (255, 176, 72)
ERR = (255, 108, 108)


class Display:
    """Framebuffer writer.

    /dev/fb0 on this device is the DRM fbdev emulation, and mmap on it yields a
    zero-length mapping, so frames are pushed with write(2) instead — the
    pixels land correctly and can be read back from the same fd.
    """

    def __init__(self, device=FB_DEVICE):
        self.width = FB_WIDTH
        self.height = FB_HEIGHT
        self._fh = open(device, "r+b", buffering=0)
        self._size = FB_HEIGHT * FB_STRIDE
        self.image = Image.new("RGB", (self.width, self.height), BG)
        self.draw = ImageDraw.Draw(self.image)
        self._fonts = {}

    def font(self, size=14, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            path = FONT_BOLD if bold else FONT_REGULAR
            if not os.path.exists(path):
                path = FONT_FALLBACK
            try:
                self._fonts[key] = ImageFont.truetype(path, size)
            except OSError:
                self._fonts[key] = ImageFont.load_default()
        return self._fonts[key]

    def clear(self, color=BG):
        self.image.paste(color, (0, 0, self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    def text(self, xy, text, size=14, color=FG, bold=False):
        self.draw.text(xy, text, font=self.font(size, bold), fill=color)
        return self.text_width(text, size, bold)

    def text_width(self, text, size=14, bold=False):
        return int(self.draw.textlength(text, font=self.font(size, bold)))

    def rect(self, box, outline=None, fill=None, width=1):
        self.draw.rectangle(box, outline=outline, fill=fill, width=width)

    def line(self, xy, color=MUTED, width=1):
        self.draw.line(xy, fill=color, width=width)

    def flush(self):
        arr = np.asarray(self.image).astype(np.uint16)
        rgb = ((arr[:, :, 0] & 0xF8) << 8) | ((arr[:, :, 1] & 0xFC) << 3) | (arr[:, :, 2] >> 3)
        data = rgb.astype("<u2").tobytes()
        self._fh.seek(0)
        written = 0
        while written < len(data):
            written += os.write(self._fh.fileno(), data[written:])

    def close(self):
        try:
            self._fh.close()
        except OSError:
            pass
