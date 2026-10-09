# 外出先から trainer を使う（設計書）

状態：**コード側は実装済み**（2026-10-09）。Cloudflare 側の設定（手順 5）と trainer の常駐化はユーザーの作業待ち。
疑問が出たら、この文書の「決めたこと」と「未決」を見て、未決はユーザーに確認する。

## 目的

- スキマ時間にスマホから練習できるようにする。主に使うのはライティング・リーディング・進捗
- 検索エンジンや bot にクロールされない。認証は「重くない」程度（毎回のパスワード入力は避けたい）
- 外から練習した時間も、学習時間として journal に残す

## 決めたこと（結論）

**Cloudflare Tunnel で手元の Mac mini の FastAPI をそのまま公開し、Cloudflare Access（メールのワンタイム PIN）で認証する。**
全タブをそのまま公開する。

```
スマホのブラウザ
  │ https://<hostname>  （hostname は公開リポジトリに書かない）
  ▼
Cloudflare Access ── 未ログインならメール OTP のログイン画面（bot はここで止まる）
  │ ログイン済み：Cf-Access-Authenticated-User-Email ヘッダーを付けて転送
  ▼
Cloudflare Tunnel（cloudflared、Mac mini 上で常駐）
  │ http://localhost:8765
  ▼
FastAPI（trainer serve）── 手元と同じ全機能
  │
  ▼
practice/<技能>/... に session.json 保存（今までと同じ場所）
```

### なぜこの構成か

| 観点 | Tunnel + Access（採用） | Workers に移植（不採用） |
|---|---|---|
| コード変更 | robots.txt・noindex ヘッダー・スマホ幅の CSS 程度 | バックエンドの書き直し（Python → Workers）、保存先を D1/KV に変更、git への同期が必要 |
| 練習ログ | `practice/` にそのまま残る → `trainer summary`・journal・mistakes の運用が無変更 | クラウドの DB からローカルへ同期する仕組みが別途いる |
| API キー | Gemini・ElevenLabs のキーは Mac mini の `.env` に留まる | Workers の secret に複製 |
| 前提 | Mac mini が起きていること（`pmset` で sleep=0 を確認済み。常時稼働） | なし |
| 費用 | Tunnel・Access（Zero Trust Free）は無料。ドメインは既存のもの | Workers 無料枠 |

「最小限の変更で目的を達成する」方針に合うのは前者。Mac mini が落ちていると使えないのが唯一の弱点だが、常時稼働機なので許容する。
Tailscale 等の VPN は、スマホ側にクライアントが要るのでスキマ時間の手軽さで劣る。

### 公開範囲：全タブ

- ユーザーの判断：音声のタブ（スピーキング・リスニング・教材・発音・Versant）は外からはまず使わないが、わざわざ隠すほどではない
- Access で本人しか入れないので、API ごとの制限は設けない。ElevenLabs のクレジットを外から使われる心配も Access で塞がれる
- Tunnel は HTTPS なので、スマホでもマイク（`getUserMedia`）は動くはず。動作保証まではしない

### 認証の軽さと、クロール対策

- Access のポリシー：**ユーザーの Gmail 1 件だけ Allow**、ID プロバイダは One-time PIN（メールで 6 桁コード）
- セッション期間を最長（1 か月）にする → スマホでは月に 1 回コードを入れるだけ
- bot はログイン画面しか見られないので、クロール対策は Access だけで実質足りる。保険として
  - 全レスポンスに `X-Robots-Tag: noindex, nofollow` を付ける（手元の localhost に付いても害はないので条件分けしない）
  - `/robots.txt` で全拒否（dist に静的ファイルとして置く）
  - hostname は意味のないランダムな文字列にし、**公開リポジトリ（README・この文書・コード）には書かない**。cloudflared の設定は `~/.cloudflared/` にあり、リポジトリ外
- JWT の検証はしない。サーバーは `127.0.0.1` にしか bind しておらず、外からの到達経路は tunnel だけだから。強めたいなら cloudflared の ingress で `originRequest.access` を有効にすれば、コードを変えずに済む

## 実装手順（Opus へ）

CLAUDE.md の方針（最小変更・周囲のスタイルに合わせる・コメントは Why を日本語で）を守ること。

### 1. noindex ヘッダー — `apps/trainer/src/trainer/server.py`

- `@app.middleware("http")` で全レスポンスに `X-Robots-Tag: noindex, nofollow` を付ける

### 2. `robots.txt` — `apps/trainer/web/public/robots.txt`

```
User-agent: *
Disallow: /
```

Vite は `public/` をそのまま `dist/` にコピーする。

### 3. スマホ幅の確認と最小の CSS 調整 — `apps/trainer/web/src/styles.css`

- headless Chrome で `--window-size=390,844` のスクリーンショットを撮って確認（CLAUDE.md の手順）。少なくとも `#writing`・`#reading`・`#progress`
- 想定される直し：タブが 8 個あるので `nav.tabs` の横スクロール（`overflow-x:auto; white-space:nowrap`）、ヘッダーの折り返し、ボタンのタップ領域。split レイアウトは `max-width:900px` で 1 カラムになる既存ルールがあるので、それで足りるか見る
- `index.html` に `<meta name="viewport" ...>` があるか確認
- ここは「使えること」が目標。デザインの作り込みはしない

### 4. 外からの練習時間の記録（ハートビート方式）

外から練習すると Claude Code のセッションが無いので、journal の sessions に start / end が残らない。
画面が「使われている間」だけ 1 分ごとにサーバーへ通知し、その時刻の並びからセッションを組み立てる。

**画面側** — `apps/trainer/web/src/hooks/useActivity.ts`（新規）を `App.tsx` で 1 回呼ぶ

- 60 秒ごとに `POST /api/activity` を送る。ただし次の両方を満たすときだけ
  - `document.visibilityState === "visible"`（裏に回したタブは数えない）
  - 直近 2 分以内に操作があった（`keydown`・`pointerdown`・`scroll`・`input` を `window` で拾って時刻を覚える）。PC で開きっぱなしのタブを数えないため
- 手元か外かは画面では判定しない。常に送り、サーバーが判定する（画面に分岐を作らない）
- 失敗は無視する（トーストも出さない）

**サーバー側** — `apps/trainer/src/trainer/activity.py`（新規）、`server.py` にルート追加

- `POST /api/activity`：リクエストに `Cf-Access-Authenticated-User-Email` ヘッダーがあるときだけ、現在時刻（分単位 `HH:MM`）を記録する。無ければ何もせず 204
  - 手元の練習は Claude Code のセッションで数えているので、外からの分だけ数える（二重計上を避ける）
- 保存先：`practice/activity/YYYY/MM/YYYY-MM-DD.json`、中身は `{"date": "YYYY-MM-DD", "minutes": ["16:31", "16:32", ...]}`（重複は入れない、`storage.lock` で書く）
  - `storage.SKILLS` には入れない（技能ではなく、進捗の集計対象でもないため）。json なので git 管理される
- `sessions(date) -> list[{"start", "end", "minutes"}]`：`minutes` を並べ、**間が 10 分を超えたら別セッション**に分ける。`end` は最後の通知 + 1 分、`minutes` は end − start

**CLI** — `summary.py`

- `trainer summary [日付]` の出力に「## 外からの練習」を足し、セッションを `HH:MM–HH:MM（N 分）` で並べる。無ければ節ごと出さない

**journal への転記** — ルート直下の `CLAUDE.md` に追記する

- journal を仕上げるとき（終了の合図）に、`trainer summary` の「外からの練習」を sessions に `{ start: "HH:MM", end: "HH:MM", source: remote }` で書き、`total_minutes` に含める
- 開始の合図・その日最初のセッションのときも、**前回の journal 以降の日付**について `practice/activity/` を見て、外から練習しただけで journal が無い日があれば journal を作って転記する（さかのぼり）
- Claude Code のセッションと時間が重なったら、重なった分は数えない（同じ時間を二重に数えない）


### 5. 常駐化（リポジトリ外の作業。手順だけ README に書く）

1. `brew install cloudflared`
2. `cloudflared tunnel login` → `cloudflared tunnel create trainer`
3. `~/.cloudflared/config.yml`：

   ```yaml
   tunnel: <tunnel-id>
   credentials-file: /Users/<user>/.cloudflared/<tunnel-id>.json
   ingress:
     - hostname: <hostname>
       service: http://localhost:8765
     - service: http_status:404
   ```

4. `cloudflared tunnel route dns trainer <hostname>`（ドメインのネームサーバーが Cloudflare であることは確認済み）
5. `sudo cloudflared service install` → LaunchDaemon として常駐
6. Zero Trust ダッシュボード（初回は Free プランを選ぶ。カード登録を求められることがあるが 0 円）→ Access → Applications → Self-hosted：
   - Application domain = `<hostname>`、Session Duration = 1 month
   - Policy：Allow、Include = Emails = ユーザーの Gmail
   - Identity providers = One-time PIN のみ
7. trainer 本体の常駐：今は Claude のセッション開始時に `nohup uv run --project apps/trainer trainer serve --no-browser` で起こしている。外から使うなら Mac 起動時に自動で上がる必要があるので、LaunchAgent（`~/Library/LaunchAgents/com.ayakix.trainer.plist`）を 1 つ足す
   - 実行するのは `start.command` と同じ判定（dist が古ければ build → `uv run trainer serve --no-browser`）をするスクリプト。`start.command` 自体はブラウザを開く用なので、`apps/trainer/serve.sh` のように分ける
   - CLAUDE.md の「開始の合図」の起動チェック（curl で確認→止まっていれば起動）はそのまま残しておけば、LaunchAgent と二重起動にならない（ポートが使用中なら curl が通るため）
   - 注意：trainer はコードを変えても自動では再起動しない。外から最新の画面を使うには、変更後に LaunchAgent を `launchctl kickstart -k` で再起動する。この手順も README に書く
8. `.env` への追加は不要。hostname は `.env` にも書かなくてよい（サーバーは hostname を知らなくて動く）

### 6. テスト — `apps/trainer/tests/test_remote.py`（新規）

`TestClient` で外部 API を呼ばずに確認できる範囲：

- `GET /api/config` のレスポンスに `X-Robots-Tag` が付く
- `POST /api/activity`：ヘッダー無しなら何も保存しない。ヘッダー有りなら当日のファイルに分が追加され、同じ分の 2 回目は重複しない（`conftest.py` は `storage.settings` だけを tmp に差し替えるので、`activity.py` は保存先を `storage.settings.practice_dir` から取ること。`config.settings` を直接 import するとテストが本物の `practice/` に書く）
- `activity.sessions()`：`["10:00","10:01","10:02","10:20"]` → `10:00–10:03`（3 分）と `10:20–10:21`（1 分）の 2 つ
- 手動：`curl -H 'Cf-Access-Authenticated-User-Email: x@example.com' localhost:8765/api/config`

### 7. README への追記 — `apps/trainer/README.md`

「外出先から使う」節を足し、この文書へのリンクと、手順 5 の要約（hostname・ドメインは書かない）を置く。

## 完了条件

- [ ] スマホのブラウザで `https://<hostname>` を開くとメール OTP → 全タブが出る
- [ ] 外からリーディングを 1 本解くと、Mac mini の `practice/reading/...` に session.json ができ、`trainer summary` に載る
- [ ] 外から 5 分ほど操作すると `trainer summary` の「外からの練習」に出て、終了の合図で journal の sessions に `source: remote` で入る
- [ ] 手元のブラウザで操作しても `practice/activity/` には何も増えない
- [ ] 手元の `http://localhost:8765` は今まで通り使える
- [ ] `uv run pytest` が通る。390px 幅のスクリーンショットで、ライティング・リーディング・進捗が操作できる見た目になっている
- [ ] Mac mini を再起動しても cloudflared と trainer が自動で上がる

## 決定済み

- ドメイン：Cloudflare 管理の既存ドメイン（ネームサーバーが Cloudflare であることを確認済み）。名前はリポジトリに書かない
- サブドメイン：意味のないランダムな 12 文字。値はユーザーが控えており、リポジトリには書かない
- OTP を受けるメール：ユーザーの Gmail
- 公開範囲：全タブ
- 外からの練習時間：ハートビート方式（実装手順 4）。練習ログからの推定や自己申告は、短めに出る・漏れるので不採用

## 未決（ユーザーに確認）

なし（2026-10-09 時点）

## あとで検討（今回はやらない）

- PWA の manifest を付けてホーム画面に置く（アイコンから 1 タップで開く）
- リーディングの文章を Gemini で事前に数本作っておき、生成待ち（数秒）をなくす
- Mac mini の死活監視（UptimeRobot などで `https://<hostname>` を見る。Access のログイン画面が返れば生きている）
