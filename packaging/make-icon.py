#!/usr/bin/env python3
"""Generate the store icon for 便携OCR.

The store policy requires a square PNG between 128 and 512 px, and the icon
must not be shared with another package or dpkg will conflict. We draw a
camera-and-document mark from scratch so the file is unique to this app.
"""

import os
import sys

from PIL import Image, ImageDraw

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "images")

BG_TOP = (26, 32, 48)
BG_BOTTOM = (12, 15, 22)
ACCENT = (72, 198, 255)
PAPER = (238, 244, 255)
INK = (46, 58, 82)
LENS = (255, 176, 72)


def rounded(draw, box, radius, **kw):
    draw.rounded_rectangle(box, radius=radius, **kw)


def main():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded background with a vertical gradient.
    grad = Image.new("RGB", (1, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / float(size - 1)
        gd.point((0, y), fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t)
                                   for i in range(3)))
    grad = grad.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=54, fill=255)
    img.paste(grad.convert("RGBA"), (0, 0), mask)

    # Document sheet.
    rounded(d, (44, 40, 168, 196), 12, fill=PAPER)
    for i, y in enumerate(range(74, 176, 20)):
        w = 104 if i % 3 else 76
        d.rounded_rectangle((62, y, 62 + w, y + 9), radius=4, fill=INK)

    # Camera body in front, bottom-right.
    rounded(d, (92, 122, 224, 216), 22, fill=(24, 30, 46),
            outline=ACCENT, width=4)
    d.ellipse((130, 140, 186, 196), fill=LENS)
    d.ellipse((143, 153, 173, 183), fill=(24, 30, 46))
    d.ellipse((150, 160, 166, 176), fill=ACCENT)
    # Viewfinder bump.
    rounded(d, (140, 108, 180, 128), 8, fill=(24, 30, 46), outline=ACCENT, width=4)

    # Capture ray from lens to sheet.
    d.line((112, 96, 88, 62), fill=ACCENT, width=4)
    d.polygon([(84, 56), (94, 62), (84, 68)], fill=ACCENT)

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    for px in (128, 256, 512):
        out = os.path.join(OUT_DIR, "icon-%d.png" % px)
        img.resize((px, px), Image.LANCZOS).convert("RGB").save(out, "PNG")
        print("wrote", out)


if __name__ == "__main__":
    sys.exit(main())
