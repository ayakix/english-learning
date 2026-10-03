#!/bin/bash
# ダブルクリックで起動（macOS）
set -e
cd "$(dirname "$0")"
root="$(cd ../.. && pwd)"
if [ ! -f "$root/.env" ]; then
  cp "$root/.env.example" "$root/.env"
  echo "リポジトリ直下に .env を作成しました。APIキーを記入して保存し、もう一度 start.command を開いてください。"
  open -e "$root/.env"
  read -n 1 -s -r -p "（何かキーを押すと閉じます）"
  exit 0
fi
# すでに起動中ならブラウザを開くだけ
PORT=$(grep -E '^PORT=' "$root/.env" | cut -d= -f2); PORT=${PORT:-8765}
if curl -s -o /dev/null "http://localhost:$PORT/api/config"; then
  open "http://localhost:$PORT"; exit 0
fi
# 画面のソースが更新されていたらビルドし直す（git pull 後に古い画面のままにならないように）
if [ ! -d web/dist ] || [ -n "$(find web/src web/index.html -newer web/dist -print -quit)" ]; then
  (cd web && npm install --silent && npm run build)
fi
exec uv run trainer
