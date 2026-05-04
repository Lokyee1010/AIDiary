#!/usr/bin/env bash
# AI 心情树洞 — 一键启动
# 用法：
#   1) 在 Finder 里双击此文件（首次会被 Gatekeeper 拦，去"系统设置 → 隐私与安全性"点"仍要打开"即可）
#   2) 或在终端里：bash ~/ai-mood-hole/start.command

set -u
cd "$(dirname "$0")"

# === 配置 ===
# KIMI_API_KEY 从环境变量读取，请先在 ~/.zshrc 中加一行：
#   export KIMI_API_KEY="sk-..."
# 然后重开终端或 source ~/.zshrc 后再运行此脚本。
: "${KIMI_API_KEY:?未设置 KIMI_API_KEY 环境变量，请先在终端 export KIMI_API_KEY=sk-... 或写进 ~/.zshrc}"
PYTHON=".venv/bin/python"
CLOUDFLARED="$HOME/.local/bin/cloudflared"

# === 健康检查 ===
[ -x "$PYTHON" ]      || { echo "找不到 $PYTHON，venv 可能被删了。"; exit 1; }
[ -x "$CLOUDFLARED" ] || { echo "找不到 $CLOUDFLARED，cloudflared 没装。"; exit 1; }

echo "=================================================="
echo "  🌳 AI 心情树洞 启动中..."
echo "=================================================="

# === 启动 Flask（后台）===
"$PYTHON" app.py >/tmp/ai-mood-hole-flask.log 2>&1 &
FLASK_PID=$!
trap 'echo; echo "正在关闭..."; kill $FLASK_PID 2>/dev/null; exit 0' INT TERM EXIT

# 等待 Flask 就绪
for i in 1 2 3 4 5 6 7 8; do
  if curl -sf -o /dev/null http://127.0.0.1:5000/; then
    echo "✓ Flask 已就绪 (PID $FLASK_PID)"
    break
  fi
  if [ "$i" = "8" ]; then
    echo "✗ Flask 启动失败，看 /tmp/ai-mood-hole-flask.log"
    exit 1
  fi
  sleep 1
done

# === 启动隧道（前台，输出可见）===
echo
echo "正在打通公网隧道，请等 10~30 秒..."
echo "下面会出现一行 https://xxx.trycloudflare.com"
echo "复制它，发给朋友就能用。"
echo
echo "—— 想关闭：直接关这个窗口，或按 Ctrl+C —— "
echo "=================================================="
echo

exec "$CLOUDFLARED" tunnel --url http://127.0.0.1:5000
