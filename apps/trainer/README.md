# English Trainer — 英語 4 技能の練習とスコア記録

4 技能を 1 画面のタブで練習し、スコアを日々記録するローカルアプリです。

| タブ | 練習 | スコア |
|---|---|---|
| スピーキング | 写真を英語で描写 → AI添削と理想の文章 → ElevenLabsの手本音声でシャドーイング → 発音評価。「テスト」は TOEIC の写真描写と同じ形式（準備 45 秒・解答 30 秒） | 発音評価の最高点（発音・流暢さ・抑揚・再現度）。テストはテストの点 |
| リスニング | ディクテーション：レベル別の 5 文を聞いて書き取る | 単語の一致率（AI ではなく機械的に採点） |
| ライティング | お題（メール・意見・出来事の説明）に英文で答える → 添削 | 観点別の採点（課題・文法・語彙・構成）と CEFR |
| リーディング | 250〜350 語の文章を読んで 5 問に答える | 正答率と WPM（1 分あたりの語数） |
| 教材 | 記事と音声で、聞く（3 問）→ 書き取る（3 文）→ 読む（5 問・WPM）。取得元は AI 教材（約 1 分半）と VOA（約 5 分）から選ぶ | 「聞く」の正答率と「書き取り」の一致率の平均 |
| 発音 | リンキング（音のつながり）8 型 × 25 例と、ミニマルペア（L/R など）8 組 × 20 ペア。聞いて真似する | （記録しない） |
| Versant | 復唱（300 文・長さで 4 段階）と即答（200 問）。テキストを隠して音声だけで練習する | （記録しない） |
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
| `1`〜`8` | タブ切り替え |
| `N` | 新しい問題（写真・セット・お題・文章） |
| スピーキング | `T` テスト（`Space` で開始 / 早めに終える） / `M` 話す / `⌘↵` 添削 / `Space` 再生 / `R` シャドーイング録音 / `⇧R` リピート録音 / `E` AI評価 |
| リスニング | `Tab` もう一度聞く（入力中でも使える） / `Enter` 答え合わせ |
| ライティング | `⌘↵` 提出 |
| リーディング | `Space` 読み始める / 読み終えた |
| 教材 | `Space` 全体を再生 / 一時停止 / `←` `→` 5 秒戻る・進む / `[` `]` 速度 / `Tab` 書き取る文を再生 |
| 発音 | `↑` `↓` 例を選ぶ / `Space` フレーズを再生 / `Enter` 例文を再生 / `←` `→` ミニマルペアの左・右を再生 |
| Versant | `↑` `↓` 問題を選ぶ / `Space` 再生 / `V` テキストを表示 |

- シャドーイング録音は手本の音がマイクに入らないよう **ヘッドホン推奨**。
- リーディングは「読み始める」を押すまで本文を隠し、「読み終えた」までの時間で WPM を計ります（設問を解く時間は含めない）。

## データ

`practice/<技能>/YYYY/MM/<id>/session.json` に、問題・回答・採点結果が保存されます。各タブの「履歴」から過去の練習を開けます。

- どの技能の session.json も `result: {score, details}` を持ち、進捗の集計に使います
- git で管理するのは **session.json だけ**（公開リポジトリのため。写真はライセンスと容量、音声は容量の理由で管理外）
- スピーキングの写真は取得元の URL を残しているので、clone し直した後も自動で取り直します

### VOA の教材

- 使うのは **VOA の記者が書いた記事だけ**（米政府の職員の作品なのでパブリックドメイン。本文を session.json に残せる）
  - AP・ロイター・AFP の記事を VOA が書き直したものは通信社の著作権が残るので、記事末尾のクレジットで除く（`src/trainer/sources/voa.py`）
- 記事は Words and Their Stories / Health & Lifestyle / Arts & Culture / American Stories / Science & Technology の一覧からランダムに選び、一度使った記事は選ばない
- 音声は VOA の mp3 をそのまま使う（git 管理外。無ければ元の URL から取り直す）
- 書き取りの区間は、ElevenLabs Scribe の単語タイムスタンプを本文の文に対応づけて決める（1 本で Scribe を約 5〜7 分ぶん使う）
- 教材の取得元は `src/trainer/sources/` に 1 モジュールずつ置く。ELLLO などを足すときはここに追加する

### スピーキングテスト（content/speaking/）

- 写真 100 枚（Unsplash）と模範解答（60〜80 語、TOEIC の解答例の文体）は **Claude が選んで書いた**。手本音声は ElevenLabs（声はランダム）
- 「テスト」ボタンで、まだ解いていない写真が出る。開始するまで写真はぼかしてあり、準備 45 秒 → 合図の音で 30 秒録音 → Gemini が TOEIC の 0〜3 と 100 点満点で採点
- 採点前は模範解答と手本音声を返さない。採点後は、添削と模範解答の音声でのシャドーイングに進める
- 写真・音声が無いとき（clone 直後など）は `uv run trainer stock speaking` で取り直す

### 発音・リンキング（content/linking/）

- 8 つの型（子音＋母音・母音＋母音・同じ子音・t の弾音化・脱落・同化・弱形・h の脱落）× 25 例の、フレーズ・聞こえ方（カタカナ）・例文は **Claude が書いた**。音声は ElevenLabs（米国の声からランダム）
- 表記：`‿` は音がつながる所、`()` はほとんど聞こえない音（例：`nex(t)‿week`、`tell‿(h)im`）
- 音声が無いとき（clone 直後など）は `uv run trainer stock linking` で作り直す（クレジットを使う）
- 今は聞いて真似するだけで、記録は残さない。クイズ形式などは後から足す

### 復唱・即答・ミニマルペア（content/drills/）

- 復唱（`repeats`）・即答（`short-answers`）・ミニマルペア（`minimal-pairs`）の例題は **Claude が書いた**。音声は ElevenLabs（復唱・即答は採用済みの声すべて、ミニマルペアは米国の声からランダム）
- どの種類も `items.json` の各例題が `audio: {枠: {text, file}}` を持ち、`src/trainer/drills.py` が枠ごとに音声を作る。種類を足すときは `KINDS` に加える
- 音声が無いときは `uv run trainer stock drills [種類 ...]` で作る（クレジットを使う）

### AI 教材（content/generated/）

- 題材 200 本（時計・ワイン・航空・アプリ開発・ランニング・子育て・自然科学・金融）。一覧は `content/generated/topics.md`
- 原稿（`script.json` の turns）と設問（`quiz.json`）は **Claude が書く**。音声は ElevenLabs（`eleven_v4_turbo`）で作り、文の間 0.35 秒・話者の切り替わり 0.8 秒の無音を足す
- 原稿を書き足したら、音声にする：

```sh
uv run trainer stock build            # 原稿があって audio.mp3 の無いものを全部
uv run trainer stock build wt001 wn003 # ID を指定
```

- 音声（`audio.mp3`）は git 管理外。TTS の結果は `.cache/stock/` に残るので、間の長さを変えて作り直すだけならクレジットはかからない
- 練習で一度使った題材は選ばれない（「教材」タブの分野の横に残り本数が出る）
- 手本音声が無いセッションは「音声を作る」で作り直せます（ElevenLabs のクレジットを消費します）

journal・mistakes への転記や、推移の確認には CLI を使います：

```sh
uv run trainer summary            # 今日の練習結果（Markdown）
uv run trainer summary 2026-10-03
uv run trainer progress           # 4 技能の週ごとの平均スコア（Markdown の表）
```

## 設定（.env）

- `GEMINI_MODEL` … 既定 `gemini-flash-latest`。存在しないモデル名でも、利用可能な Flash 系に自動で切り替えます。
- `ELEVENLABS_MODEL` … 既定 `eleven_v4_turbo`。`eleven_v4`（最高品質）/ `eleven_flash_v2_5`（高速・安価）。変えると、同じ文章でも手本音声を作り直します
- `PRACTICE_DIR` … 練習ログの保存先を変えたいとき（既定はリポジトリ直下の `practice`）

## 終了

ターミナルのウィンドウで `Ctrl + C`、またはウィンドウを閉じる。
