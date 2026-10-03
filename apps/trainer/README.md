# English Trainer — 英語 4 技能の練習とスコア記録

4 技能を 1 画面のタブで練習し、スコアを日々記録するローカルアプリです。

| タブ | 練習 | スコア |
|---|---|---|
| スピーキング | 写真を英語で描写 → AI添削と理想の文章 → ElevenLabsの手本音声でシャドーイング → 発音評価 | 発音評価の最高点（発音・流暢さ・抑揚・再現度） |
| リスニング | ディクテーション：レベル別の 5 文を聞いて書き取る | 単語の一致率（AI ではなく機械的に採点） |
| ライティング | お題（メール・意見・出来事の説明）に英文で答える → 添削 | 観点別の採点（課題・文法・語彙・構成）と CEFR |
| リーディング | 250〜350 語の文章を読んで 5 問に答える | 正答率と WPM（1 分あたりの語数） |
| 進捗 | 4 技能の週ごとの平均スコアのグラフと表 | |

- バックエンド：Python（uv + FastAPI）`src/trainer/`（技能ごとに 1 モジュール）
- フロントエンド：Vite + React + TypeScript `web/`（`src/pages/` に技能ごとのページ）
- 練習ログ：リポジトリ直下の `practice/<技能>/YYYY/MM/<id>/`

## 準備（初回のみ）

1. **APIキーを用意**して、リポジトリ直下の `.env` に書く（項目は `.env.example`）
   - Gemini: https://aistudio.google.com/apikey
   - ElevenLabs: https://elevenlabs.io/app/settings/api-keys（Text to Speech と Voices の読み取りを許可）
   - Unsplash（任意）: https://unsplash.com/oauth/applications → New Application → Access Key
2. [uv](https://docs.astral.sh/uv/) と Node.js（22 以上）を入れておく

## 起動

**`start.command` をダブルクリック**（画面のビルドとサーバー起動をまとめて行い、ブラウザで http://localhost:8765 を開きます）。

ターミナルから起動する場合：

```sh
cd web && npm install && npm run build && cd ..
uv run trainer            # http://localhost:8765
```

ブラウザでマイクの使用を許可してください（Chrome 推奨）。

- タブは URL のハッシュで開けます（例：`http://localhost:8765/#listening`）
- `?s=<セッションID>` を付けると、そのタブで特定の練習を開きます（例：`/?s=20261003-143120#listening`）
- 練習のレベル（B1 / B2 / C1）と声は、右上の「設定」で全タブ共通に変えられます

### 開発

```sh
uv run trainer serve --no-browser   # API（:8765）
cd web && npm run dev               # 画面（:5173。API は :8765 に転送）
uv run pytest                       # バックエンドのテスト（外部 API は呼ばない）
```

## キーボードショートカット

画面右上の ⌨ で一覧を出せます。主なもの：

| キー | 動作 |
|---|---|
| `1`〜`5` | タブ切り替え |
| `N` | 新しい問題（写真・セット・お題・文章） |
| スピーキング | `M` 話す / `⌘↵` 添削 / `Space` 再生 / `R` シャドーイング録音 / `⇧R` リピート録音 / `E` AI評価 |
| リスニング | `Tab` もう一度聞く（入力中でも使える） / `Enter` 答え合わせ |
| ライティング | `⌘↵` 提出 |
| リーディング | `Space` 読み始める / 読み終えた |

- シャドーイング録音は手本の音がマイクに入らないよう **ヘッドホン推奨**。
- リーディングは「読み始める」を押すまで本文を隠し、「読み終えた」までの時間で WPM を計ります（設問を解く時間は含めない）。

## データ

`practice/<技能>/YYYY/MM/<id>/session.json` に、問題・回答・採点結果が保存されます。各タブの「履歴」から過去の練習を開けます。

- どの技能の session.json も `result: {score, details}` を持ち、進捗の集計に使います
- git で管理するのは **session.json だけ**（公開リポジトリのため。写真はライセンスと容量、音声は容量の理由で管理外）
- スピーキングの写真は取得元の URL を残しているので、clone し直した後も自動で取り直します
- 手本音声が無いセッションは「音声を作る」で作り直せます（ElevenLabs のクレジットを消費します）

journal・mistakes への転記や、推移の確認には CLI を使います：

```sh
uv run trainer summary            # 今日の練習結果（Markdown）
uv run trainer summary 2026-10-03
uv run trainer progress           # 4 技能の週ごとの平均スコア（Markdown の表）
```

## 設定（.env）

- `GEMINI_MODEL` … 既定 `gemini-flash-latest`。存在しないモデル名でも、利用可能な Flash 系に自動で切り替えます。
- `ELEVENLABS_MODEL` … `eleven_multilingual_v2`（高品質）/ `eleven_flash_v2_5`（高速・安価）
- `PRACTICE_DIR` … 練習ログの保存先を変えたいとき（既定はリポジトリ直下の `practice`）

## 終了

ターミナルのウィンドウで `Ctrl + C`、またはウィンドウを閉じる。
