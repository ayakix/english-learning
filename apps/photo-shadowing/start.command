#!/bin/bash
# ダブルクリックで起動（macOS）
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env を作成しました。APIキーを記入して保存し、もう一度 start.command を開いてください。"
  open -e .env
  read -n 1 -s -r -p "（何かキーを押すと閉じます）"
  exit 0
fi
# すでに起動中ならブラウザを開くだけ
PORT=$(grep -E '^PORT=' .env | cut -d= -f2); PORT=${PORT:-8765}
if curl -s -o /dev/null "http://localhost:$PORT/api/config"; then
  open "http://localhost:$PORT"; exit 0
fi
exec /usr/bin/env python3 app.py
