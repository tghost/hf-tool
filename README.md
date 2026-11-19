# 便携OCR (hf-tool)

离线拍照取字应用，为 [CardputerZero](https://cardputer.cc/) 设计。

用设备自带摄像头拍下文字，在本机离线识别中文与英文，结果直接在 320×170
屏幕上分页查看，并可保存为 TXT 文件。全程不联网、不上传任何图片。

## 特点

- **全离线**：包内自带 tesseract 5 + `chi_sim` / `eng` 语言包，不依赖系统安装，
  不需要网络连接。
- **拍摄质量门控**：拍照后先检查亮度、对比度和饱和度。画面全黑、纯白过曝或
  完全平坦时直接提示重拍，避免把一堆噪点丢给识别引擎（那会白等近 100 秒）。
- **光照与模糊增强**：识别前做背景光照归一化（除以自身模糊副本），再全局
  对比度拉伸，最后统一缩放到 800px 宽。实测阴影页和失焦页因此都能达到完整
  识别率，而不是只认出一两个字。
- **分页阅读**：结果按 320×170 屏幕分页，用实体键盘翻页。
- **一键导出**：保存为 `~/Documents/ocr-<时间戳>.txt`。

## 硬件与平台约束

设备只有 **352 MiB 内存**（不是标称的 512MB），所以选型按 352 MiB 计算：
不用大型常驻服务、不用重型框架、不跑本地大模型。

经实测，**onnxruntime 在这台设备上跑 OCR 会被 OOM killer 杀死**（引擎级
工作集问题，调参救不回来），因此引擎固定为 tesseract 5。整条链路峰值
RSS 约 47 MB。

相机走 `picamera2` 直接采集，不复用官方的 C++/LVGL 相机应用。
交互全部走 46 键 TCA8418 实体键盘（设备没有 touch 输入），
按键按标准 Linux 键码解析。

## 界面按键

| 动作 | 按键 |
| --- | --- |
| 上下选择 | `2` / `8`（也接受 FN 方向键、SYM 小键盘） |
| 确认 | `Enter` |
| 翻页 | `4` / `6`（结果页） |
| 保存 TXT | `E` |
| 返回 | `Esc` |

## 目录结构

```
src/hf_ocr/
  app.py       主流程：首页 → 拍照 → 质量门控 → OCR → 分页 → 保存
  camera.py    picamera2 预览与静帧采集
  imaging.py   质量统计、门控、光照归一化、缩放
  ocr.py       tesseract 调用与文本清洗
  textview.py  320×170 分页排版
  display.py   /dev/fb0 RGB565 直写
  keys.py      evdev 原始事件解析
  export.py    TXT 导出
packaging/
  build-deb.sh 构建 arm64 .deb
  selftest.py  无界面自检（耗时与峰值 RSS）
```

## 构建

```bash
bash packaging/build-deb.sh
# 产物：build/hf-tool_1.0.0_arm64.deb
```

包内自带 tesseract 运行时，需要先准备 `tessroot/`（`libtesseract.so.5`、
`libleptonica.so.6` 以及 `eng/chi_sim/osd.traineddata`），
路径由 `TESS_SRC` 环境变量指定。

## 自检

```bash
python3 packaging/selftest.py /path/to/document.png
```

输出各阶段耗时与峰值 RSS，便于在 352 MiB 设备上发现回归。

## 许可

MIT
