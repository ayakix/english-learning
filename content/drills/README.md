# 音声つきドリル

「Versant」タブ（復唱・即答）と「発音」タブ（ミニマルペア）で使う例題です。

| 種類 | 中身 | 件数 | 声 |
|---|---|---|---|
| `repeats/` | 復唱（Versant の Repeats）。聞いた文をそのまま繰り返す。語数でレベル 1〜4 | 300 文 | 採用済みの声すべてからランダム |
| `short-answers/` | 即答（Versant の Short Answer Questions）。一般常識の質問に 1〜2 語で答える。`answers` は正解として受け付ける答え | 200 問 | 採用済みの声すべてからランダム |
| `minimal-pairs/` | 1 音だけ違う 2 語（L/R・B/V・TH/S・F/H・S/SH・æ/ʌ・iː/ɪ・ɜːr/ɑːr・ɔː） | 8 組 × 20 ペア | 米国の声からランダム |

| ファイル | 作り手 | git |
|---|---|---|
| `<種類>/items.json`（例題・声・音声のファイル名） | 例題：Claude | 管理する |
| `<種類>/<ID>/model_*.mp3`（音声） | `trainer stock drills` | 管理外 |

- 生成した音声は Scribe で文字起こしして、読み間違いが無いことを確かめた
- 音声が無い場合は `uv run --project apps/trainer trainer stock drills` で作り直せます（クレジットを使います）
