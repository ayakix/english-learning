# CLAUDE.md

このリポジトリは、ユーザーが AI と一緒に英語を学び直し、2027-04 に英会話で困らないレベルを目指す実験の場である。
README.md と curriculum/roadmap.md も参照すること。

## 学習時間の記録

### 合言葉

| 合図 | 受け付ける入力 | Claude の動作 |
|---|---|---|
| 開始 | `Hello` / `hello` / `開始` | `date` で現在時刻を取得し、当日の journal に新しいセッションの start を記録する。続けて「今日の流れ」を伝える |
| 終了 | `See you` / `see you` / `終了` | `date` で現在時刻を取得して end を記録し、journal を最終版に仕上げる。記録されない練習の申告を求める |

- 大文字小文字は問わない
- 開始の合図を受けたら、練習アプリ（apps/trainer）が起動しているかを `curl -s -o /dev/null http://localhost:8765/api/config` で確かめ、止まっていればバックグラウンドで起動する（ユーザーが毎回起動しなくて済むように）
  - 画面のソースが dist より新しければ、先に `cd apps/trainer/web && npm run build` でビルドし直す（start.command と同じ判定）
  - 起動：`nohup uv run --project apps/trainer trainer serve --no-browser > /dev/null 2>&1 &`
    - Bash の run_in_background で起動すると、時間制限（既定 30 分）で止められるため、nohup で切り離す
  - ブラウザは開かない。今日の流れでタブの URL を伝える
- その日最初のセッションは、合言葉がなくても会話開始時点を学習開始として扱う
  - `.claude/hooks/session-start.sh`（SessionStart hook）が journal を作成し、開始時刻を記録する
- 時刻は必ず `date` コマンドで取得する。推測で書かない

### 今日の流れ（開始の合図のあと）

curriculum/roadmap.md の「1 日・1 週間の型」に沿って、今日やることを ①〜④ の具体的なメニューにして伝える。

- 曜日で ③ メインを決める。2026-10-05 から何週目かで ① 発音と ② 復唱の段階を決める
- 直近の journal の「## 記録されない練習」を読み、続きを指定する（例：リンキングの次の型、復唱の次の ID 範囲とレベル、苦手だった組の復習）
- 教材・スピーキングテストは `trainer summary` で直近の結果を見て、弱い所があれば一言添える
- タブの URL（http://localhost:8765/#versant など）も添える

### 記録されない練習（終了の合図のあと）

発音と Versant のタブは練習ログが残らないので、終了の合図を受けたら、その日の分を次の形で申告してもらう。

- 申告してほしい項目を、今日の流れで指定したメニューに合わせて具体的に聞く（例：「リンキング 子音＋母音 lk001-lk013 はできた？苦手だったものは？」「復唱 rp001-rp020 で言えたのは何文？」）
- 申告を journal の「## 記録されない練習」に roadmap の書式で書く。時間は sessions に含まれるので別に足さない
- trainer で記録される練習（教材・スピーキングなど）は `trainer summary` で自動で取れるので聞かない

### 記録の対象

- 英語学習に使った時間はすべて含める（システム開発・設計の壁打ちも含む）
- Claude Code 以外での学習（trainer 単体での練習、英会話、他のアプリなど）はユーザーの自己申告で追記する

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
  - { minutes: 15, source: trainer, note: 自己申告 }
total_minutes: 0
---

## やったこと
## 記録されない練習
## 間違えたこと・気づき
## Claude との進め方メモ
```

間違えた内容は `mistakes/` にも転記し、後から振り返れるようにする。

## 練習アプリ（apps/trainer）

- 起動・構成は `apps/trainer/README.md` を参照
- 4 技能のタブ（スピーキング・リスニング・ライティング・リーディング）、記事と音声で聞く→書き取る→読むを通す「教材」（VOA と AI 教材）、スコアの推移を見る「進捗」がある
  - スピーキングには TOEIC の写真描写と同じ形式の「テスト」がある
  - 「発音」タブでは、リンキング（音のつながり）とミニマルペアの例題を聞いて真似できる
  - 「Versant」タブには、Versant 形式の復唱と即答のドリルがある
- 教材の原稿・設問（content/generated）、スピーキングテストの写真選び・模範解答（content/speaking）、発音・ドリルの例題（content/linking・content/drills）は Claude が書く。Gemini はアプリ動作中の採点・設問生成に使う
- 練習ログは `practice/<技能>/YYYY/MM/<id>/session.json` に保存される（session.json だけ git 管理。写真・音声は管理外）
  - どの技能も `result.score`（0〜100）を持ち、進捗の集計に使う。AI の採点はぶれるので、週の平均で傾向を見る
- journal を仕上げるときは、その日の練習結果を次のコマンドで取得して「やったこと」「間違えたこと」に反映する
  - `uv run --project apps/trainer trainer summary [YYYY-MM-DD]`
  - 添削で直された表現・発音で指摘された単語・聞き取れなかった語は `mistakes/` にも転記する
- 週の推移は `uv run --project apps/trainer trainer progress` で確認できる
- Web の画面を作ったり変えたりしたら、ユーザーに渡す前に headless Chrome でスクリーンショットを撮って見た目を確認する
  - `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --window-size=1280,900 --screenshot=<scratchpad>/x.png <URL>`

## 秘密情報

- API キーはリポジトリ直下の `.env` に置き、絶対にコミットしない（公開リポジトリのため）。項目は `.env.example` を参照
- ユーザーにキーを入力してもらうときは、チャットに貼らず `.env` を直接編集してもらう（会話のログに残るため）
