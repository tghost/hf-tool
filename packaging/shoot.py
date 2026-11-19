#!/usr/bin/env python3
"""Render each application screen on the real device and save the screenshots.

The store requires 320x170 screenshots showing the real app. Reading the
framebuffer back is racy here (other panel writers tear the frame), so we save
the application's own render buffer instead — it is the exact image the panel
displays, without the tearing artefacts.
"""

import os
import sys
import time

sys.path.insert(0, "/usr/share/APPLaunch/apps/hf-tool/lib")

from hf_ocr.app import App  # noqa: E402

OUT_DIR = "/home/tghost/ocrtest"

SAMPLE_TEXT = (
    "理赔材料交接单\n\n"
    "单据编号 : LP20261120-0847\n"
    "投保产品 : 人保健康百万医疗2026\n\n"
    "本次赔付金额 : 12,860.50\n"
    "出险日期 : 2026年11月18日\n\n"
    "医院名称 : 某某市第一人民医院\n"
    "科室 : DAH  住院天数 : 3天\n\n"
    "联系电话 : 13800138000"
)


def save(app, name):
    path = os.path.join(OUT_DIR, "shot-%s.png" % name)
    app.display.image.save(path, "PNG")
    print("saved", path, app.display.image.size)
    return path


def main():
    app = App()
    try:
        app.render_home(0)
        time.sleep(0.3)
        save(app, "home")

        app.last_text = SAMPLE_TEXT
        app.viewer.set_text(app.last_text)
        app.viewer.render(title="识别结果", status="4/6 翻页  E 保存  ESC 返回")
        time.sleep(0.3)
        save(app, "result")

        # A short result so the paging indicator shows more than one page.
        long_text = "\n".join("第 %d 行：示例识别文本 %d" % (i, i) for i in range(1, 19))
        app.viewer.set_text(long_text)
        app.viewer.render(title="识别结果", status="4/6 翻页  E 保存  ESC 返回")
        time.sleep(0.3)
        save(app, "paging")
    finally:
        app.display.close()


if __name__ == "__main__":
    main()
