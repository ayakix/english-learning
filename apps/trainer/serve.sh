#!/bin/bash
# 常駐用の起動スクリプト（LaunchAgent から呼ぶ。外出先から Cloudflare 経由で使うため、Mac の起動時に上げておく）
# start.command はブラウザを開く手元用なので、ビルドの判定だけ同じにして分けている
set -e
# launchd の PATH は最小限なので、uv と npm の場所を足す
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")"
# 画面のソースが更新されていたらビルドし直す（start.command と同じ判定）
if [ ! -d web/dist ] || [ -n "$(find web/src web/index.html web/public -newer web/dist -print -quit)" ]; then
  (cd web && npm install --silent && npm run build)
fi
exec uv run trainer serve --no-browser
