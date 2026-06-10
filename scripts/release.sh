#!/bin/bash
# 本地打包：py2app 生成 .app，再做成可拖拽安装的 .dmg。
#   bash scripts/release.sh
# 产物：dist/ukabu-n1.app 和 dist/ukabu-n1.dmg
set -euo pipefail
cd "$(dirname "$0")/.."

APP="ukabu-n1"
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY="python3"

echo "▸ 生成图标 icon.icns"
if [ ! -f assets/icon.icns ] || [ assets/icon.png -nt assets/icon.icns ]; then
  rm -rf assets/icon.iconset && mkdir -p assets/icon.iconset
  for s in 16 32 128 256 512; do
    sips -z $s $s assets/icon.png --out assets/icon.iconset/icon_${s}x${s}.png >/dev/null
    d=$((s*2)); sips -z $d $d assets/icon.png --out assets/icon.iconset/icon_${s}x${s}@2x.png >/dev/null
  done
  iconutil -c icns assets/icon.iconset -o assets/icon.icns
  rm -rf assets/icon.iconset
fi

echo "▸ py2app 打包"
rm -rf build dist
"$PY" setup.py py2app >/dev/null

echo "▸ 生成 dmg"
STAGE="$(mktemp -d)"
cp -R "dist/$APP.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "dist/$APP.dmg"
hdiutil create -volname "$APP" -srcfolder "$STAGE" -ov -format UDZO "dist/$APP.dmg" >/dev/null
rm -rf "$STAGE"

echo "✅ 完成：dist/$APP.app  +  dist/$APP.dmg"
