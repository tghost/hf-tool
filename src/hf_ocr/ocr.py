"""Tesseract wrapper with the runtime bundled inside the application package.

The .deb ships tesseract 5, leptonica and the eng/chi_sim/osd traineddata
files under the application's own prefix, so no system-wide tesseract install
is required and the Store package stays self-contained.
"""

import os
import re
import subprocess
import time

# The app payload lives next to this module: <prefix>/lib/hf_ocr/ocr.py, with the
# bundled tesseract under <prefix>/tesseract. Deriving the prefix from __file__
# keeps this working regardless of how the app was launched.
_HERE = os.path.dirname(os.path.abspath(__file__))
APP_PREFIX = os.environ.get("HF_OCR_PREFIX") or os.path.dirname(os.path.dirname(_HERE))
TESS_BIN = os.path.join(APP_PREFIX, "tesseract", "bin", "tesseract")
TESSDATA = os.path.join(APP_PREFIX, "tesseract", "share", "tessdata")
LIB_DIR = os.path.join(APP_PREFIX, "tesseract", "lib")

# Text that must survive OCR round-trips. Kept generic on purpose: this is a
# general-purpose OCR tool, not a document-field extractor.
_PUNCT_FIXES = [
    (re.compile(r"[“”„‟]"), '"'),
    (re.compile(r"[‘’‚‛]"), "'"),
    (re.compile(r"[‐-―]"), "-"),
    (re.compile(r"\s{3,}"), "  "),
]

# Long digit runs are frequently broken by a stray space during OCR; glue them
# back together without assuming any particular document layout.
_DIGIT_RUN = re.compile(r"(?<=\d)[ \t]+(?=\d)")


def available():
    return os.path.exists(TESS_BIN)


def _env():
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = LIB_DIR + ":" + env.get("LD_LIBRARY_PATH", "")
    env["TESSDATA_PREFIX"] = TESSDATA
    env.setdefault("OMP_THREAD_LIMIT", "1")
    return env


def run(image, langs="chi_sim+eng", psm="3", timeout=90):
    """Run tesseract on a PIL image and return (text, elapsed_seconds)."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="hfocr-") as tmp:
        src = os.path.join(tmp, "in.png")
        out = os.path.join(tmp, "out")
        image.save(src, "PNG")
        cmd = [
            TESS_BIN, src, out,
            "-l", langs,
            "--psm", psm,
            "--dpi", "300",
            "-c", "preserve_interword_spaces=1",
        ]
        start = time.time()
        try:
            proc = subprocess.run(cmd, env=_env(), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "", timeout
        elapsed = time.time() - start
        txt_path = out + ".txt"
        text = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        if not text and proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            if err:
                text = ""
        return text, elapsed


def postprocess(text):
    """Clean up common OCR artefacts on Chinese documents."""
    out = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, repl in _PUNCT_FIXES:
        out = pattern.sub(repl, out)
    out = _DIGIT_RUN.sub("", out)
    lines = [ln.strip() for ln in out.split("\n")]
    return "\n".join(ln for ln in lines if ln)
