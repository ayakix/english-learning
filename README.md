# english-learning

英語の **スピーキング力** を AI と一緒に伸ばす実験の記録です（Learning in public）。

- 教材は AI（LLM / TTS）で生成し、練習用のツールも自分で作る
- 写真を英語で描写 → 添削 → 手本音声でシャドーイング、を日々の練習の柱にする
- 学習時間・練習結果・間違いを記録し、後から振り返れるようにする

## ディレクトリ構成

```
curriculum/              学習の骨組み
journal/                 日々の学習記録（時間・内容・振り返り）
mistakes/                間違いノート
practice/shadowing/      Photo Shadowing の練習ログ（session.json。写真・音声は git 管理外）
apps/photo-shadowing/    写真描写 × シャドーイング練習アプリ（FastAPI + React）
scripts/                 CLI ツール
```

## 使っている AI

- Claude Code：学習のメイン（記録・振り返り・ツール開発）
- Gemini：文字起こし・添削・発音評価（Photo Shadowing 内）
- ElevenLabs：TTS（シャドーイングの手本音声）
