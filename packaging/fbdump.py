#!/usr/bin/env python3
"""Dump the CardputerZero framebuffer to a PNG.

Used to capture the real application screen for the store screenshots, so the
listing shows the actual UI rather than a mock-up.
"""

import os
import sys

import numpy as np
from PIL import Image

FB_DEVICE = "/dev/fb0"
WIDTH, HEIGHT = 320, 170
STRIDE = WIDTH * 2


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb.png"
    size = HEIGHT * STRIDE
    with open(FB_DEVICE, "rb") as fh:
        fh.seek(0)
        raw = fh.read(size)
        if len(raw) < size:
            raw = raw + b"\x00" * (size - len(raw))
    arr = np.frombuffer(raw, dtype="<u2").reshape(HEIGHT, STRIDE // 2)
    r = (arr >> 11) & 0x1F
    g = (arr >> 5) & 0x3F
    b = arr & 0x1F
    rgb = np.stack([(r * 255 // 31), (g * 255 // 63), (b * 255 // 31)], axis=-1)
    Image.fromarray(rgb.astype("uint8"), "RGB").save(out, "PNG")
    print("saved", out)


if __name__ == "__main__":
    main()
