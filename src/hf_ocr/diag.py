"""Diagnostics: show what the camera actually saw, and dump evidence to disk.

Two independent failure modes look identical from the outside ("the result
is garbage"), but need completely different fixes:

1. The captured frame is out of focus / too small / rotated -> the OCR
   engine is fine, the input is not.
2. The OCR engine produced low-confidence noise -> the frame is fine, the
   engine needs a confidence filter.

So the app renders the captured frame onto the 320x170 panel before running
OCR (the user can then photograph the screen and we know immediately), and
writes a small evidence bundle to ~/Documents/ocrdiag for a deeper look.
"""

import os

import numpy as np
from PIL import Image, ImageOps

DIAG_DIR = os.environ.get("HF_OCR_DIAG_DIR",
                           os.path.expanduser("~/Documents/ocrdiag"))


def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
    return path


def thumbnail(array, width, height):
    """Return a contrast-boosted grayscale thumbnail of a captured frame.

    Autocontrast is applied so the picture stays readable on the tiny panel
    even when the raw frame is dim.
    """
    gray = Image.fromarray(np.asarray(array, dtype=np.uint8)[:, :, :3]).convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=(2, 2))
    return gray.resize((width, height), Image.LANCZOS)


def focus_score(array):
    """Estimate how sharp the frame is.

    Uses the variance of a Laplacian-like operator: a blurred image has
    almost no high-frequency energy, a sharp one has a lot. Only useful as a
    relative signal between two shots of the same scene, not an absolute
    scale.
    """
    gray = np.asarray(array, dtype=np.float32)[:, :, :3]
    lum = gray[:, :, 0] * 0.299 + gray[:, :, 1] * 0.587 + gray[:, :, 2] * 0.114
    lap = (lum[1:-1, 1:-1] * 4.0
           - lum[:-2, 1:-1] - lum[2:, 1:-1]
           - lum[1:-1, :-2] - lum[1:-1, 2:])
    return float(lap.var())


def dump(name, raw=None, prepared=None, meta=None, tsv=None):
    """Write the evidence bundle for one capture.

    Every file is overwritten on each capture, so the directory never grows
    past a handful of hundred KB.
    """
    try:
        directory = _ensure_dir(DIAG_DIR)
        if raw is not None:
            Image.fromarray(np.asarray(raw, dtype=np.uint8)[:, :, :3]).save(
                os.path.join(directory, "raw.png"))
        if prepared is not None:
            prepared.save(os.path.join(directory, "prepared.png"))
        if tsv:
            with open(os.path.join(directory, "ocr.tsv"), "w",
                      encoding="utf-8") as fh:
                fh.write(tsv)
        if meta:
            with open(os.path.join(directory, "meta.txt"), "w",
                      encoding="utf-8") as fh:
                for key in sorted(meta):
                    fh.write("%s = %s\n" % (key, meta[key]))
        return directory
    except Exception:
        return None


def font_report():
    """Report which fonts the renderer actually resolved.

    A missing CJK font does not raise, it silently draws hollow boxes, which
    a user would very reasonably describe as "the text is garbage".
    """
    from .display import FONT_BOLD, FONT_FALLBACK, FONT_REGULAR

    lines = []
    for label, path in (("regular", FONT_REGULAR), ("bold", FONT_BOLD)):
        lines.append("font_%s=%s exists=%s" % (label, path, os.path.exists(path)))
    lines.append("font_fallback=%s exists=%s"
                 % (FONT_FALLBACK, os.path.exists(FONT_FALLBACK)))
    return "\n".join(lines)
