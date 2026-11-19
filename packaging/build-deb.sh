#!/usr/bin/env bash
# Build the hf-tool .deb for CardputerZero (arm64).
#
# Layout follows the official APPLaunch convention:
#   /usr/share/APPLaunch/applications/hf-tool.desktop
#   /usr/share/APPLaunch/bin/hf-tool
#   /usr/share/APPLaunch/apps/hf-tool/...        (app payload + tesseract runtime)
#   /usr/share/APPLaunch/share/images/hf-tool.png
#
# The package is self-contained: it carries the tesseract 5 runtime, leptonica
# and the eng/chi_sim/osd traineddata inside the app directory, so the device
# needs no system-wide tesseract install and the Store package stands alone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BUILD="${BUILD:-$ROOT/build}"
DEB="$BUILD/hf-tool_1.0.0_arm64.deb"
TESS_SRC="${TESS_SRC:-/data/tghost/file/projects/cardputerzero-lab/tessroot}"

# The project dir lives on a CIFS share that forces 0777, which dpkg-deb
# rejects for the DEBIAN control dir, so staging happens on local disk.
STAGE="$(mktemp -d /tmp/hf-tool-stage.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

PKG=hf-tool
VERSION=1.0.0
REVISION=m5stack1
ARCH=arm64
MAINTAINER="Hao Fan <wang.h.fan@outlook.com>"
DESCRIPTION="Offline camera OCR for CardputerZero: capture text with the built-in camera, recognise Chinese and English locally, browse the result on the 320x170 screen and export it as a TXT file."

PREFIX=/usr/share/APPLaunch
APPDIR="$PREFIX/apps/$PKG"

mkdir -p "$STAGE/DEBIAN" \
         "$STAGE$PREFIX/applications" \
         "$STAGE$PREFIX/bin" \
         "$STAGE$PREFIX/share/images" \
         "$STAGE$APPDIR/lib" \
         "$STAGE$APPDIR/tesseract/bin" \
         "$STAGE$APPDIR/tesseract/lib" \
         "$STAGE$APPDIR/tesseract/share/tessdata" \
         "$STAGE/usr/share/doc/$PKG"

# --- application code -------------------------------------------------------
cp -r "$ROOT/src/hf_ocr" "$STAGE$APPDIR/lib/"
find "$STAGE$APPDIR/lib" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$STAGE$PREFIX/bin/$PKG" <<EOF
#!/bin/sh
PREFIX=$PREFIX
APP=$APPDIR
export LD_LIBRARY_PATH="\$APP/tesseract/lib:\${LD_LIBRARY_PATH}"
export TESSDATA_PREFIX="\$APP/tesseract/share/tessdata"
export HF_OCR_PREFIX="\$APP"
export PYTHONPATH="\$APP/lib:\${PYTHONPATH}"
exec /usr/bin/python3 -m hf_ocr.app "\$@"
EOF
chmod 0755 "$STAGE$PREFIX/bin/$PKG"

# --- tesseract runtime ------------------------------------------------------
if [ ! -x "$TESS_SRC/usr/bin/tesseract" ]; then
  echo "tesseract source tree not found at $TESS_SRC" >&2
  exit 1
fi
install -m 0755 "$TESS_SRC/usr/bin/tesseract" "$STAGE$APPDIR/tesseract/bin/"
cp -a "$TESS_SRC"/usr/lib/aarch64-linux-gnu/libtesseract.so.5* "$STAGE$APPDIR/tesseract/lib/"
cp -a "$TESS_SRC"/usr/lib/aarch64-linux-gnu/libleptonica.so.6* "$STAGE$APPDIR/tesseract/lib/"
for L in eng chi_sim osd; do
  install -m 0644 "$TESS_SRC/usr/share/tesseract-ocr/5/tessdata/$L.traineddata" \
    "$STAGE$APPDIR/tesseract/share/tessdata/"
done

# --- desktop entry and icon -------------------------------------------------
cat > "$STAGE$PREFIX/applications/$PKG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=便携OCR
Comment=离线文字识别：拍照取字，支持中英文
Exec=$PREFIX/bin/$PKG
Icon=share/images/$PKG.png
Terminal=false
Categories=Utility;TextTools;
StartupNotify=false
EOF

if [ -f "$ROOT/assets/images/icon-128.png" ]; then
  install -m 0644 "$ROOT/assets/images/icon-128.png" "$STAGE$PREFIX/share/images/$PKG.png"
else
  echo "icon missing at $ROOT/assets/images/icon-128.png" >&2
  exit 1
fi

# --- package metadata -------------------------------------------------------
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION-$REVISION
Architecture: $ARCH
Maintainer: $MAINTAINER
Section: APPLaunch
Priority: optional
Homepage: https://github.com/tghost/hf-tool
Installed-Size: $(du -ks "$STAGE" | cut -f1)
Depends: python3, python3-numpy, python3-pil, python3-picamera2, python3-numpy
Description: $DESCRIPTION
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
for grp in video input; do
  if getent group "$grp" >/dev/null 2>&1 && id -u pi >/dev/null 2>&1; then
    usermod -aG "$grp" pi || true
  fi
done
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postrm"

cp "$HERE/../LICENSE" "$STAGE/usr/share/doc/$PKG/LICENSE" 2>/dev/null || true
# Ship the headless self-test so the app can be verified on the device itself.
cp "$HERE/selftest.py" "$STAGE/usr/share/doc/$PKG/selftest.py" 2>/dev/null || true

chmod 0755 "$STAGE/DEBIAN"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB"
echo "built: $DEB"
dpkg-deb --info "$DEB" | sed -n '1,14p'
du -h "$DEB"
