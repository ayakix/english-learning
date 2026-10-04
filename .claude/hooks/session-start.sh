#!/bin/bash
# その日最初のセッションを自動で学習開始として記録する。
# Claude が記録を忘れても開始時刻が残るように、hook 側で journal を作る。
# 2 回目以降のセッションは合言葉（Hello / 開始）で Claude が記録する（CLAUDE.md 参照）。
set -eu

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
today=$(date +%Y-%m-%d)
now=$(date +%H:%M)
journal="$root/journal/$(date +%Y)/$(date +%m)/$today.md"

if [ -f "$journal" ]; then
  echo "[学習記録] 今日の journal は既にあります: ${journal#$root/}（現在 ${now}）。新しいセッションを学習として記録するのは、ユーザーが合言葉（Hello / 開始）を言ったときだけ。"
  exit 0
fi

mkdir -p "$(dirname "$journal")"
cat > "$journal" <<JOURNAL
---
date: $today
sessions:
  - { start: "$now", end: null, source: claude-code }
total_minutes: 0
---

## やったこと

## 記録されない練習

## 間違えたこと・気づき

## Claude との進め方メモ
JOURNAL

echo "[学習記録] 今日最初のセッションのため、学習開始 ${now} として ${journal#$root/} を作成しました。ユーザーにその旨を一言伝えること。"
