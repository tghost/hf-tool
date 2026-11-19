#!/usr/bin/env python3
"""Headless self-test for the bundled 便携OCR runtime on the device.

Runs every stage outside the interactive loop and reports timings plus peak
RSS, so a regression on the 352 MiB device shows up as numbers, not vibes.
"""

import json
import os
import resource
import sys
import time

# Prefer the installed APPLaunch payload, and fall back to the source tree so
# the same self-test works both on the device and in a checkout.
for candidate in ("/usr/share/APPLaunch/apps/hf-tool/lib",
                   os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src")):
    if os.path.isdir(os.path.join(candidate, "hf_ocr")):
        sys.path.insert(0, candidate)
        break

from hf_ocr import export, imaging, ocr  # noqa: E402

from PIL import Image  # noqa: E402

RESULTS = []


def record(name, value):
    RESULTS.append({"step": name, "value": value})
    print("[%s] %s" % (name, value))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/ocrtest/doc_real.png")
    record("input", src)

    if not os.path.exists(src):
        record("fatal", "input missing")
        return 1

    t0 = time.time()
    img = Image.open(src).convert("RGB")
    import numpy as np
    array = np.asarray(img)
    record("load_seconds", round(time.time() - t0, 2))
    record("input_size", "%dx%d" % img.size)

    t0 = time.time()
    stats = imaging.check_quality(array)
    record("quality_ok", True)
    record("quality", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in stats.items()})
    record("quality_seconds", round(time.time() - t0, 3))

    t0 = time.time()
    prepared = imaging.prepare(array)
    record("prepare_seconds", round(time.time() - t0, 2))
    record("prepared_size", "%dx%d" % prepared.size)

    t0 = time.time()
    text, elapsed = ocr.run(prepared)
    record("ocr_seconds", round(elapsed, 2))
    record("ocr_wall_seconds", round(time.time() - t0, 2))

    clean = ocr.postprocess(text)
    record("ocr_lines", len([ln for ln in clean.split("\n") if ln.strip()]))
    record("ocr_chars", len(clean))
    record("ocr_head", clean.split("\n")[0] if clean else "")

    t0 = time.time()
    path = export.export_text(clean)
    record("export_path", path)
    record("export_seconds", round(time.time() - t0, 2))

    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    record("peak_rss_kb", peak_kb)
    record("peak_rss_mb", round(peak_kb / 1024.0, 1))

    print("---OCR_TEXT---")
    print(clean)
    print("---END---")
    print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
