"""Tesseract wrapper with the runtime bundled inside the application package.

The .deb ships tesseract 5, leptonica and the eng/chi_sim/osd traineddata
files under the application's own prefix, so no system-wide tesseract install
is required and the Store package stays self-contained.
"""

import os
import re
import subprocess
import time
import unicodedata

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


# Words below this confidence are evidence that the engine is guessing rather
# than reading. On a blurred frame tesseract does not return "nothing" -- it
# invents plausible-looking characters, which is exactly what a user reports
# as "the output is all garbage". The threshold is applied to a whole line
# (the mean confidence of the words on it), never to individual words:
# dropping single low-confidence words also destroys real text, because a
# correct line can contain one uncertain character.
MIN_LINE_CONF = 60.0


def _is_cjk(ch):
    """True for CJK ideographs, CJK punctuation and fullwidth forms."""
    if not ch:
        return False
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return True
    code = ord(ch)
    return (0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF
            or 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF)


def _tsv_line_confidences(tsv_text):
    """Return the mean confidence of every text line in a tesseract TSV.

    The TSV carries one row per word, with the line identified by the
    (block, par, line) id triple. Rows with an empty text field are layout
    markers and are ignored.
    """
    sums = {}
    counts = {}
    order = []
    for row in tsv_text.splitlines()[1:]:
        fields = row.split("\t")
        if len(fields) < 12:
            continue
        word = fields[11].strip()
        if not word:
            continue
        try:
            key = (int(fields[2]), int(fields[3]), int(fields[4]))
            conf = float(fields[10])
        except ValueError:
            continue
        if key not in sums:
            sums[key] = 0.0
            counts[key] = 0
            order.append(key)
        sums[key] += conf
        counts[key] += 1
    return [(sums[k] / counts[k]) for k in order]


def _filter_by_confidence(text, tsv_text):
    """Drop text lines the engine was not confident about.

    The plain-text output is the source of truth for the wording and the
    spacing (tesseract's TSV output splits Chinese into single characters
    and loses the original spaces, so rebuilding the text from it would
    insert spaces that were never there). The TSV is used purely as a
    quality signal: the Nth non-empty text line is matched with the Nth
    line of the TSV and dropped when that line's mean confidence is too low.

    When the counts do not line up -- which happens when the engine emitted
    a line the TSV does not describe -- the text is left untouched rather
    than risk dropping real content.
    """
    confs = _tsv_line_confidences(tsv_text)
    if not confs:
        return text
    lines = text.split("\n")
    out = []
    idx = 0
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        if idx >= len(confs):
            out.append(line)
            continue
        if confs[idx] < MIN_LINE_CONF:
            idx += 1
            continue
        out.append(line)
        idx += 1
    return "\n".join(out)


def _parse_tsv(tsv_text):
    """Rebuild the recognised text from a tesseract TSV.

    Kept for diagnostics only: the TSV splits Chinese into single
    characters and does not carry the original word spacing, so the plain
    text output is preferred for the actual result.
    """
    lines = []
    current = ""
    current_key = None
    for row in tsv_text.splitlines()[1:]:
        fields = row.split("\t")
        if len(fields) < 12:
            continue
        try:
            key = (int(fields[2]), int(fields[3]), int(fields[4]))
        except ValueError:
            continue
        word = fields[11].strip()
        if not word:
            continue
        if key != current_key:
            if current:
                lines.append(current)
            current = ""
            current_key = key
        current = _join_words(current, word)
    if current:
        lines.append(current)
    return "\n".join(lines)


def _join_words(prev, word):
    """Join two TSV words, gluing adjacent CJK characters together."""
    if not prev:
        return word
    if _is_cjk(prev[-1]) and _is_cjk(word[0]):
        return prev + word
    return prev + " " + word


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
            "-c", "tessedit_create_tsv=1",
            "-c", "tessedit_create_txt=1",
        ]
        start = time.time()
        try:
            proc = subprocess.run(cmd, env=_env(), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "", timeout
        elapsed = time.time() - start

        txt_path = out + ".txt"
        tsv_path = out + ".tsv"
        text = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        if text and os.path.exists(tsv_path):
            with open(tsv_path, "r", encoding="utf-8", errors="replace") as fh:
                text = _filter_by_confidence(text, fh.read())
        return text, elapsed


def postprocess(text):
    """Clean up common OCR artefacts on Chinese documents."""
    out = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, repl in _PUNCT_FIXES:
        out = pattern.sub(repl, out)
    out = _DIGIT_RUN.sub("", out)
    lines = [ln.strip() for ln in out.split("\n")]
    return "\n".join(ln for ln in lines if ln)
