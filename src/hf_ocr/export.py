"""Export helper: save the recognized text as a plain TXT file."""

import os
import time

EXPORT_DIR = os.environ.get("HF_OCR_EXPORT_DIR", os.path.expanduser("~/Documents"))
EXT_TXT = ".txt"


def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
    return path


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def export_text(text, directory=EXPORT_DIR, ext=EXT_TXT):
    """Write the recognized text to a timestamped .txt file."""
    directory = _ensure_dir(directory)
    path = os.path.join(directory, "ocr-%s%s" % (_stamp(), ext))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
    return path
