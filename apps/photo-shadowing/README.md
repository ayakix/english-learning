# Photo Shadowing — 写真説明 × シャドーイング練習

写真を見て英語で話す → AI添削と理想の文章 → ElevenLabsの手本音声でシャドーイング → 録音をAIが発音評価、を1画面・キーボード中心で回すローカルアプリです。

- バックエンド：Python（uv + FastAPI）`src/photo_shadowing/`
- フロントエンド：Vite + React + TypeScript `web/`
- 練習ログ：リポジトリ直下の `practice/shadowing/YYYY/MM/<id>/`

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
uv run photo-shadowing            # http://localhost:8765
```

ブラウザでマイクの使用を許可してください（Chrome 推奨）。`?s=<セッションID>` を付けると、そのセッションを開きます。

### 開発

```sh
uv run photo-shadowing serve --no-browser   # API（:8765）
cd web && npm run dev                       # 画面（:5173。API は :8765 に転送）
uv run pytest                               # バックエンドのテスト（外部 API は呼ばない）
```

## 練習の流れ

| ステップ | 操作 |
|---|---|
| 写真を出す | `N`（写真の下のテーマ欄にキーワードを入れると絞り込み。Unsplash のキーが必要） |
| 英語で説明 | `M` で録音開始 → 話す → `M` で停止（自動で文字起こし。手直しもOK） |
| 添削 | `⌘ Enter` → 修正点・理想の文章・使える表現が出て、手本音声が自動生成 |
| 聴く | `Space` 再生/停止、`↑↓` で文を選択、`A` で全文、`L` でループ、`[` `]` で速度 |
| シャドーイング録音 | `R`：手本と同時に話す（自動で停止・保存） |
| リピート録音 | `⇧R`：手本を聴く → ピッ → 一人で話す |
| 確認 | `P` 自分の声、`C` 手本→自分の聴き比べ |
| AI評価 | `E`：総合・発音・流暢さ・抑揚・再現度のスコアと、単語ごとの改善ポイント |

- 文ごとにベストスコアが表示されるので、低い文を重点的に練習できます。
- 設定で「録音後に自動でAI評価」をオンにすると、`R` だけで録音→評価まで進みます。
- シャドーイング録音は手本の音がマイクに入らないよう **ヘッドホン推奨**。

## データ

`practice/shadowing/YYYY/MM/<id>/` に写真・手本音声・自分の録音（WAV）・添削/評価結果（session.json）が保存されます。「履歴」から過去の写真に戻って続きができます。

- git で管理するのは **session.json だけ**（公開リポジトリのため。写真はライセンスと容量、音声は容量の理由で管理外）
- 写真は取得元の URL を session.json に残しているので、clone し直した後も自動で取り直します
- 手本音声が無いセッションは「音声を作る」で作り直せます（ElevenLabs のクレジットを消費します）

その日の練習結果は Markdown で出力できます（journal・mistakes への転記用）：

```sh
uv run photo-shadowing summary            # 今日
uv run photo-shadowing summary 2026-10-03
```

## 設定（.env）

- `GEMINI_MODEL` … 既定 `gemini-flash-latest`。存在しないモデル名でも、利用可能な Flash 系に自動で切り替えます。
- `ELEVENLABS_MODEL` … `eleven_multilingual_v2`（高品質）/ `eleven_flash_v2_5`（高速・安価）
- `PRACTICE_DIR` … 練習ログの保存先を変えたいとき（既定はリポジトリ直下の `practice/shadowing`）
- 声・理想文のレベル（B1/B2/C1）・文の数は画面右上の「設定」から変更できます。

## 終了

ターミナルのウィンドウで `Ctrl + C`、またはウィンドウを閉じる。
