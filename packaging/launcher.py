#!/usr/bin/env python3
"""Entry point for the 便携OCR application (development / manual runs)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from hf_ocr.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
