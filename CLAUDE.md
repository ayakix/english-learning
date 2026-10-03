# CLAUDE.md

このリポジトリは、ユーザーが AI と一緒に英語のスピーキング力を伸ばす実験の場である。
README.md も参照すること。

## 学習時間の記録

### 合言葉

| 合図 | 受け付ける入力 | Claude の動作 |
|---|---|---|
| 開始 | `Hello` / `hello` / `開始` | `date` で現在時刻を取得し、当日の journal に新しいセッションの start を記録する |
| 終了 | `See you` / `see you` / `終了` | `date` で現在時刻を取得して end を記録し、journal を最終版に仕上げる |

- 大文字小文字は問わない
- その日最初のセッションは、合言葉がなくても会話開始時点を学習開始として扱う
  - `.claude/hooks/session-start.sh`（SessionStart hook）が journal を作成し、開始時刻を記録する
- 時刻は必ず `date` コマンドで取得する。推測で書かない

### 記録の対象

- 英語学習に使った時間はすべて含める（システム開発・設計の壁打ちも含む）
- Claude Code 以外での学習（Photo Shadowing 単体での練習、英会話、アプリなど）はユーザーの自己申告で追記する

### journal の運用

- 場所：`journal/YYYY/MM/YYYY-MM-DD.md`（1 日 1 ファイル）
- セッション中も適宜上書きして最新の状態に保ち、「終了」の合図で最終版にする
- `total_minutes` は sessions の合計。end が未確定のセッションは集計に含めない
- 後でブログ（Learning in public）に使うため、「何を決めたか / どう進めたか」も残す

フォーマット：

```markdown
---
date: YYYY-MM-DD
sessions:
  - { start: "HH:MM", end: "HH:MM", source: claude-code }
  - { minutes: 15, source: photo-shadowing, note: 自己申告 }
total_minutes: 0
---

## やったこと
## 間違えたこと・気づき
## Claude との進め方メモ
```

間違えた内容は `mistakes/` にも転記し、後から振り返れるようにする。

## Photo Shadowing（apps/photo-shadowing）

- 起動・構成は `apps/photo-shadowing/README.md` を参照
- 練習ログは `practice/shadowing/YYYY/MM/<id>/session.json` に保存される（session.json だけ git 管理。写真・音声は管理外）
- journal を仕上げるときは、その日の練習結果を次のコマンドで取得して「やったこと」「間違えたこと」に反映する
  - `uv run --project apps/photo-shadowing photo-shadowing summary [YYYY-MM-DD]`
  - 添削で直された表現・発音で指摘された単語は `mistakes/` にも転記する
- Web の画面を作ったり変えたりしたら、ユーザーに渡す前に headless Chrome でスクリーンショットを撮って見た目を確認する
  - `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --window-size=1280,900 --screenshot=<scratchpad>/x.png <URL>`

## 秘密情報

- API キーはリポジトリ直下の `.env` に置き、絶対にコミットしない（公開リポジトリのため）。項目は `.env.example` を参照
- ユーザーにキーを入力してもらうときは、チャットに貼らず `.env` を直接編集してもらう（会話のログに残るため）
