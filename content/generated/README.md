# AI 教材のストック

「教材」タブ（apps/trainer）で使う、リスニング教材の原稿・設問・音声です。

| ファイル | 中身 | 作り手 | git |
|---|---|---|---|
| `topics.json` / `topics.md` | 題材の一覧（200 本）とボイス | Claude | 管理する |
| `<分野>/<ID>/script.json` | 原稿（話者ごとの turns）と、音声での文ごとの区間 | 原稿：Claude、区間：TTS | 管理する |
| `<分野>/<ID>/quiz.json` | 要約・聞く 3 問・書き取り 3 文・読む 5 問 | Claude | 管理する |
| `<分野>/<ID>/audio.mp3` | 音声（ElevenLabs） | `trainer stock build` | 管理外 |

レベルは B1+（7 割）と B2（3 割）。会話形式が 3 割です。
