#!/bin/bash

# macOS double-click launcher.
# Finder runs .command files inside Terminal, so this wrapper keeps the
# existing start.sh logic while avoiding manual cd + bash commands.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

bash "$SCRIPT_DIR/start.sh"
STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
    echo "服务已退出。"
else
    echo "启动失败，请检查上面的报错信息。"
fi

echo
read -r -p "按回车键关闭此窗口..." _
exit "$STATUS"
