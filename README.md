# english-learning

英語を AI と一緒に学び直し、**半年後（2027-04）に英会話で困らないレベル** を目指す実験の記録です（Learning in public）。

- 教材は AI（LLM / TTS）で生成し、練習用のツールも自分で作る
- 4 技能（スピーキング・リスニング・ライティング・リーディング）をアプリで練習し、スコアを日々記録する
- 最終的な判定は外部テスト（Versant）で行う。詳しくは [roadmap](curriculum/roadmap.md)
- 学習時間・練習結果・間違いを記録し、後から振り返れるようにする

## ディレクトリ構成

```
curriculum/              学習の骨組み
journal/                 日々の学習記録（時間・内容・振り返り）
mistakes/                間違いノート
practice/<技能>/         練習ログ（session.json。写真・音声は git 管理外）
apps/trainer/            4 技能の練習アプリ（FastAPI + React）
```

## 使っている AI

- Claude Code：学習のメイン（記録・振り返り・ツール開発）
- Gemini：文字起こし・添削・採点・発音評価・教材生成（trainer 内）
- ElevenLabs：TTS（シャドーイングの手本音声・リスニング問題）
