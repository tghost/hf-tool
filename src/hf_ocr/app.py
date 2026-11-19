"""便携OCR — 主程序流程 for the CardputerZero.

Flow: home -> capture -> quality gate -> OCR -> paged result -> export.

Everything runs on the device itself; no network access is required.
"""

import os
import sys
import time

from . import camera as camera_mod
from . import export as export_mod
from . import imaging
from . import ocr
from .display import (ACCENT, BG, ERR, FG, MUTED, OK, WARN, Display)
from .keys import (BACK_KEYS, CONFIRM_KEYS, DOWN_KEYS, NEXT_KEYS, PREV_KEYS,
                   UP_KEYS, Keyboard)
from .textview import TextViewer

APP_TITLE = "便携OCR"
VERSION = "1.0.0"

# Below this many recognised characters the result is treated as unusable:
# a blurred or shadowed page yields a handful of stray glyphs, and showing
# those is worse than asking for a retake.
MIN_USABLE_CHARS = 12

HOME_ITEMS = [
    ("拍照识别", "capture"),
    ("保存上次结果", "export"),
    ("退出", "quit"),
]


class App:
    def __init__(self):
        self.display = Display()
        self.keys = Keyboard()
        self.viewer = TextViewer(self.display)
        self.camera = None
        self.last_text = ""
        self.last_path = None
        self.running = True

    # ---------- rendering helpers ----------

    def toast(self, message, tone="info", seconds=2.5):
        d = self.display
        d.clear()
        color = {"info": ACCENT, "ok": OK, "warn": WARN, "err": ERR}.get(tone, ACCENT)
        d.text((10, 40), APP_TITLE, size=12, color=MUTED)
        d.text((10, 62), message[:38], size=14, color=color, bold=True)
        d.text((10, 90), "请按任意键继续", size=11, color=MUTED)
        d.flush()
        self.keys.read_key(timeout=seconds)
        self.keys.read_key(timeout=0.2)

    def render_home(self, selected=0):
        d = self.display
        d.clear()
        d.rect((0, 0, d.width, 26), fill=(24, 28, 38))
        d.text((8, 6), APP_TITLE, size=14, color=ACCENT, bold=True)
        d.text((d.width - d.text_width("v" + VERSION, 10) - 6, 9), "v" + VERSION,
               size=10, color=MUTED)
        d.line((0, 26, d.width, 26), color=(48, 56, 72))
        for i, (label, _key) in enumerate(HOME_ITEMS):
            y = 42 + i * 26
            if i == selected:
                d.rect((4, y - 3, d.width - 4, y + 17), fill=(30, 38, 54))
                d.text((12, y), ">", size=13, color=ACCENT, bold=True)
            d.text((28, y), label, size=13, color=FG if i == selected else MUTED)
        d.text((8, d.height - 16), "2/8 选择  Enter 确认", size=10, color=MUTED)
        d.flush()

    def render_status(self, message, tone="info"):
        d = self.display
        # Accept either a tone name ("info"/"ok"/"warn"/"err") or an RGB tuple.
        color = {"info": ACCENT, "ok": OK, "warn": WARN, "err": ERR}.get(tone, tone)
        if not isinstance(color, tuple):
            color = ACCENT
        d.clear()
        d.text((10, 40), APP_TITLE, size=12, color=MUTED)
        d.text((10, 62), message[:38], size=13, color=color)
        d.flush()

    # ---------- actions ----------

    def do_capture(self):
        """Capture, gate on quality, run OCR and show the paged result."""
        d = self.display
        self.render_status("正在启动相机...")
        if self.camera is None:
            try:
                self.camera = camera_mod.Camera().start()
            except camera_mod.CameraError as exc:
                self.toast("相机不可用: %s" % str(exc)[:24], "err")
                return
        self.render_status("正在拍照...")
        try:
            frame = self.camera.capture()
        except camera_mod.CameraError as exc:
            self.toast("拍照失败: %s" % str(exc)[:24], "err")
            return

        # Quality gate before spending 10+ seconds on OCR.
        try:
            imaging.check_quality(frame)
        except imaging.QualityError as exc:
            hint = exc.hint or "请重拍"
            self.toast(exc.args[0][:24], "warn")
            self.render_status("提示: " + hint[:30], WARN)
            self.keys.read_key(timeout=3.0)
            return

        self.render_status("识别中，约 10 秒...")
        prepared = imaging.prepare(frame)
        text, elapsed = ocr.run(prepared)
        text = ocr.postprocess(text)
        # A frame that passes the brightness gates can still be too blurred or
        # too badly shadowed to read; in that case tesseract returns a few
        # stray characters instead of text, so warn and ask for a retake
        # rather than showing an empty result page.
        if len(text.strip()) < MIN_USABLE_CHARS:
            self.toast("识别不出文字", "warn")
            self.render_status("提示: " + "请对焦清晰、光线均匀后重拍"[:30], WARN)
            self.keys.read_key(timeout=3.0)
            return
        if not text.strip():
            self.toast("未识别到文字", "warn")
            return
        self.last_text = text
        self.viewer.set_text(text)
        self.show_result(elapsed)

    def show_result(self, elapsed=0.0):
        self.viewer.render(
            title="识别结果",
            status="4/6 翻页  E 保存  ESC 返回",
        )
        while True:
            key = self.keys.read_key(timeout=60)
            if key is None:
                continue
            if key in NEXT_KEYS:
                self.viewer.next_page()
            elif key in PREV_KEYS:
                self.viewer.prev_page()
            elif key in ("E", "e"):
                self.do_export()
            elif key in BACK_KEYS or key in ("Q", "q"):
                return
            else:
                continue
            self.viewer.render(title="识别结果",
                               status="4/6 翻页  E 保存  ESC 返回")

    def do_export(self):
        path = export_mod.export_text(self.last_text)
        self.last_path = path
        self.toast("已保存: " + os.path.basename(path), "ok")

    # ---------- main loop ----------

    def home_loop(self):
        selected = 0
        self.render_home(selected)
        while True:
            key = self.keys.read_key(timeout=120)
            if key is None:
                continue
            if key in DOWN_KEYS:
                selected = (selected + 1) % len(HOME_ITEMS)
            elif key in UP_KEYS:
                selected = (selected - 1) % len(HOME_ITEMS)
            elif key in CONFIRM_KEYS:
                action = HOME_ITEMS[selected][1]
                if action == "capture":
                    self.do_capture()
                elif action == "export":
                    if self.last_text:
                        self.do_export()
                    else:
                        self.toast("还没有识别结果", "warn")
                elif action == "quit":
                    self.running = False
                    return
            else:
                continue
            self.render_home(selected)

    def run(self):
        try:
            self.home_loop()
        except KeyboardInterrupt:
            pass
        finally:
            if self.camera:
                self.camera.stop()
            self.keys.close()
            self.display.close()


def main(argv=None):
    if not ocr.available():
        sys.stderr.write("tesseract runtime missing at %s\n" % ocr.TESS_BIN)
        return 2
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
