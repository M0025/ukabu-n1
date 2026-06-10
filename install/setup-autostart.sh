#!/bin/bash
# 配置开机自启（macOS LaunchAgent）。再次运行会覆盖更新；卸载见末尾提示。
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
LABEL="com.ukabu.n1"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$DIR/widget.py</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ 已配置开机自启：$PLIST"
echo "   取消：launchctl unload \"$PLIST\" && rm \"$PLIST\""
