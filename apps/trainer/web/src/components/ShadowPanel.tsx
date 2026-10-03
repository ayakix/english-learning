import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { api, fileUrl } from "../api";
import { useHotkeys } from "../hooks/useHotkeys";
import type { Settings } from "../hooks/useSettings";
import { useToast } from "../hooks/useToast";
import { recorder } from "../lib/recorder";
import { errMsg, sleep } from "../lib/util";
import type { Evaluation, Recording, RecMode, Session } from "../types";
import { Badge, Kbd, Panel, RecMeter, Spinner } from "./common";

export type ShadowHandle = { stopAll: () => void };

type Seg = { start: number; end: number; text: string; key: string };

const SPEED_MIN = 0.5;
const SPEED_MAX = 1.3;

export function ShadowPanel(props: {
  ref?: Ref<ShadowHandle>;
  session: Session;
  settings: Settings;
  updateSettings: (p: Partial<Settings>) => void;
  ttsLoading: boolean;
  onMakeTts: () => void;
  onRecordingsChange: (fn: (rs: Recording[]) => Recording[]) => void;
}) {
  const toast = useToast();
  const { session, settings } = props;
  const tts = session.tts;

  const [sel, setSel] = useState(-1); // 選択中の文（-1 = 全文）
  const [loop, setLoop] = useState(false);
  const [selRec, setSelRec] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [activeWord, setActiveWord] = useState(-1);
  const [banner, setBanner] = useState<string | null>(null);
  const [evalBusy, setEvalBusy] = useState<Record<number, boolean>>({});

  const modelEl = useRef<HTMLAudioElement>(null);
  const mineEl = useRef<HTMLAudioElement>(null);

  // 再生・録音の流れは await をまたぐので、古いクロージャを掴まないよう最新の値を ref から読む
  const latest = useRef({ session, settings, sel, loop });
  latest.current = { session, settings, sel, loop };

  // 区間再生：終了時刻に達したら resolve(true)、途中で止めたら resolve(false)
  const play = useRef<{ end: number; resolve: (done: boolean) => void } | null>(null);
  // 再生ループや聴き比べを途中で止めるためのトークン。止めるたびに増やし、古い流れを打ち切る
  const loopToken = useRef(0);
  const loopRunning = useRef(false);
  const rec = useRef({ abort: false, mode: "overlap" as RecMode, seg: null as Seg | null, token: 0 });

  const sentsEl = useRef<HTMLDivElement>(null);

  // セッションが変わったら選択状態をリセットする
  useEffect(() => {
    setSel(-1);
    setSelRec(null);
  }, [session.id]);

  // キーボードで文を移動したときに、選択中の文が画面外に出ないようにする
  useEffect(() => {
    sentsEl.current?.querySelector(".sent.sel")?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  // ---------------------------------------------------------------- 再生
  function segRange(): Seg {
    const { session, sel } = latest.current;
    const T = session.tts!;
    if (sel === -1) return { start: 0, end: T.sentences.at(-1)!.end + 0.3, text: T.text, key: "all" };
    const s = T.sentences[sel];
    return { start: Math.max(0, s.start - 0.06), end: s.end + 0.25, text: s.text, key: String(sel) };
  }

  function playRange(r: Seg): Promise<boolean> {
    const m = modelEl.current!;
    return new Promise((resolve) => {
      m.currentTime = r.start;
      m.playbackRate = latest.current.settings.speed;
      m.preservesPitch = true;
      play.current = { end: r.end, resolve };
      setPlaying(true);
      m.play().catch((e) => {
        toast("再生できません: " + errMsg(e), true);
        play.current = null;
        setPlaying(false);
        resolve(false);
      });
    });
  }

  function stopModel(done = false) {
    modelEl.current?.pause();
    const p = play.current;
    play.current = null;
    setPlaying(false);
    setActiveWord(-1);
    p?.resolve(done);
  }

  // timeupdate は 4Hz 程度と粗いので、単語のハイライトと区間の終了判定は rAF で行う
  useEffect(() => {
    let id = 0;
    const tick = () => {
      const m = modelEl.current;
      if (play.current && m && !m.paused) {
        const t = m.currentTime;
        const words = latest.current.session.tts?.words ?? [];
        setActiveWord(words.findIndex((w) => t >= w.s - 0.02 && t < w.e + 0.02));
        if (t >= play.current.end) stopModel(true);
      }
      id = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(id);
  }, []);

  async function togglePlay() {
    if (!tts || recorder.on) return;
    if (play.current || loopRunning.current) {
      loopToken.current++;
      loopRunning.current = false;
      stopModel();
      return;
    }
    const token = ++loopToken.current;
    do {
      loopRunning.current = latest.current.loop;
      const done = await playRange(segRange());
      if (!done || token !== loopToken.current) break;
      if (latest.current.loop) await sleep(latest.current.settings.loopGap * 1000);
    } while (latest.current.loop && token === loopToken.current);
    loopRunning.current = false;
  }

  function selectSent(i: number) {
    if (!tts) return;
    const n = tts.sentences.length;
    stopModel();
    setSel(i < -1 ? -1 : i >= n ? n - 1 : i);
  }

  function setSpeed(v: number) {
    v = Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(v * 20) / 20));
    props.updateSettings({ speed: v });
    if (modelEl.current) modelEl.current.playbackRate = v;
  }

  // ---------------------------------------------------------------- 録音
  async function shadowRec(mode: RecMode) {
    if (!tts) return;
    if (recorder.on && recorder.isOwner("shadow")) {
      rec.current.abort = true;
      finishRec();
      return;
    }
    if (recorder.isOwner("pending")) {
      rec.current.abort = true;
      stopModel();
      return;
    }
    if (recorder.on) return;
    loopToken.current++;
    loopRunning.current = false;
    stopModel();
    const r = segRange();
    const echo = latest.current.settings.echo;
    try {
      await recorder.init(echo);
    } catch (e) {
      return toast("マイクを使用できません: " + errMsg(e), true);
    }
    rec.current = { ...rec.current, abort: false, mode, seg: r };

    if (mode === "overlap") {
      setBanner("録音中… 手本と同時に話してください（R で停止）");
      await recorder.start(echo, "shadow");
      // 録音の立ち上がりを待ってから再生しないと、冒頭が録れないことがある
      await sleep(120);
      await playRange(r);
      if (recorder.on && recorder.isOwner("shadow") && !rec.current.abort) {
        // 手本が終わった直後に話し終える分の余白
        await sleep(700);
        if (recorder.on && recorder.isOwner("shadow")) finishRec();
      }
    } else {
      setBanner("手本を聴いてください…");
      recorder.owner = "pending";
      const done = await playRange(r);
      if (!done || rec.current.abort) {
        setBanner(null);
        recorder.owner = null;
        return;
      }
      await sleep(250);
      recorder.beep();
      setBanner("どうぞ！ 話してください（R で停止）");
      await recorder.start(echo, "shadow");
      // 手本の長さから話し終わる時間を見積もって自動で止める（ゆっくり話す分の余裕を持たせる）
      const dur = (r.end - r.start) / latest.current.settings.speed;
      const myToken = ++rec.current.token;
      await sleep((dur * 1.6 + 1.8) * 1000);
      if (recorder.on && recorder.isOwner("shadow") && myToken === rec.current.token) finishRec();
    }
  }

  async function finishRec() {
    rec.current.token++;
    stopModel();
    setBanner(null);
    const { blob, seconds } = recorder.stop();
    if (seconds < 0.5) return toast("録音が短すぎます");
    const seg = rec.current.seg!;
    const sid = latest.current.session.id;
    try {
      const r = await api.speaking.addRecording(sid, blob, seg.key, rec.current.mode, seg.text);
      props.onRecordingsChange((rs) => [...rs, r]);
      setSelRec(r.n);
      if (latest.current.settings.autoEval) evalRec(r);
      else toast("録音しました。P で再生 / C で聴き比べ / E でAI評価");
    } catch (e) {
      toast("録音の保存に失敗: " + errMsg(e), true);
    }
  }

  function stopAll() {
    loopToken.current++;
    loopRunning.current = false;
    stopModel();
    mineEl.current?.pause();
    if (recorder.on && recorder.isOwner("shadow")) {
      rec.current.abort = true;
      finishRec();
    }
    if (recorder.isOwner("pending")) {
      rec.current.abort = true;
      recorder.owner = null;
      setBanner(null);
    }
  }

  useImperativeHandle(props.ref, () => ({ stopAll }));

  // ---------------------------------------------------------------- 録音の一覧と評価
  const segKey = sel === -1 ? "all" : String(sel);
  const segRecs = session.recordings.filter((r) => r.seg === segKey).reverse();
  const current = segRecs.find((r) => r.n === selRec) ?? segRecs[0];

  function playMine(r = current) {
    if (!r) return toast("録音がありません");
    stopAll();
    mineEl.current!.src = fileUrl("speaking", session.id, r.file);
    mineEl.current!.play();
  }

  async function compare() {
    const r = current;
    if (!r) return toast("録音がありません");
    stopAll();
    const token = ++loopToken.current;
    const done = await playRange(segRange());
    if (!done || token !== loopToken.current) return;
    await sleep(400);
    playMine(r);
  }

  async function evalRec(r: Recording | undefined = current) {
    if (!r) return toast("評価する録音がありません");
    setSelRec(r.n);
    if (r.evaluation || evalBusy[r.n]) return;
    const sid = latest.current.session.id;
    setEvalBusy((b) => ({ ...b, [r.n]: true }));
    try {
      const ev = await api.speaking.evaluate(sid, r.n);
      props.onRecordingsChange((rs) => rs.map((x) => (x.n === r.n ? { ...x, evaluation: ev } : x)));
    } catch (e) {
      toast("評価失敗: " + errMsg(e), true);
    } finally {
      setEvalBusy((b) => ({ ...b, [r.n]: false }));
    }
  }

  useHotkeys({
    " ": togglePlay,
    l: () => setLoop((v) => !v),
    L: () => setLoop((v) => !v),
    a: () => selectSent(-1),
    A: () => selectSent(-1),
    ArrowDown: () => selectSent(sel + 1),
    ArrowRight: () => selectSent(sel + 1),
    ArrowUp: () => selectSent(sel - 1),
    ArrowLeft: () => selectSent(sel - 1),
    "[": () => setSpeed(settings.speed - 0.05),
    "]": () => setSpeed(settings.speed + 0.05),
    r: () => shadowRec("overlap"),
    R: () => shadowRec("repeat"),
    p: () => playMine(),
    P: () => playMine(),
    c: compare,
    C: compare,
    e: () => evalRec(),
    E: () => evalRec(),
    Escape: stopAll,
  });

  // 文ごとのベストスコア（低い文を重点的に練習できるように表示する）
  const best: Record<string, number> = {};
  for (const r of session.recordings)
    if (r.evaluation) best[r.seg] = Math.max(best[r.seg] ?? 0, r.evaluation.overall);

  const prevEval = current
    ? segRecs.filter((r) => r.evaluation && r.n < current.n)[0]?.evaluation ?? undefined
    : undefined;

  return (
    <Panel
      n={3}
      title="シャドーイング"
      right={
        <button className="btn sm" onClick={props.onMakeTts} disabled={props.ttsLoading}>
          🔊 {tts ? "音声を作り直す" : "音声を作る"}
        </button>
      }
    >
      {props.ttsLoading && (
        <div className="hint">
          <Spinner /> 手本音声を生成中…
        </div>
      )}
      {tts && (
        <div>
          <audio ref={modelEl} src={fileUrl("speaking", session.id, tts.file)} preload="auto" onEnded={() => play.current && stopModel(true)} />
          <audio ref={mineEl} preload="auto" />
          <div className="row" style={{ justifyContent: "space-between" }}>
            <button className={`btn sm all toggle${sel === -1 ? " on" : ""}`} onClick={() => selectSent(-1)}>
              全文{best.all != null && `（best ${best.all}）`} <Kbd>A</Kbd>
            </button>
            <span className="hint">
              文をクリックで選択 / <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> で移動
            </span>
          </div>
          <div className="sents" ref={sentsEl}>
            {tts.sentences.map((_, i) => (
              <div
                key={i}
                className={`sent${i === sel ? " sel" : ""}`}
                onClick={() => selectSent(i === sel ? -1 : i)}
              >
                <span className="no">{i + 1}</span>
                <span>
                  {tts.words.map((w, wi) =>
                    w.i === i ? (
                      <span key={wi}>
                        <span className={`w${wi === activeWord ? " on" : ""}`}>{w.t}</span>{" "}
                      </span>
                    ) : null,
                  )}
                </span>
                {best[String(i)] != null && <span className="best">best {best[String(i)]}</span>}
              </div>
            ))}
          </div>
          <div className="transport">
            <div className="grp">
              <button className="btn primary" onClick={togglePlay}>
                {playing ? "⏸ 停止" : "▶ 再生"} <Kbd>Space</Kbd>
              </button>
              <button className={`btn toggle${loop ? " on" : ""}`} onClick={() => setLoop((v) => !v)}>
                🔁 ループ <Kbd>L</Kbd>
              </button>
            </div>
            <div className="grp">
              <span className="hint">速度</span>
              <input
                type="range"
                min={SPEED_MIN}
                max={SPEED_MAX}
                step={0.05}
                value={settings.speed}
                onChange={(e) => setSpeed(+e.target.value)}
              />
              <b style={{ minWidth: 42 }}>{settings.speed.toFixed(2)}x</b>
              <Kbd>[</Kbd>
              <Kbd>]</Kbd>
            </div>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn rec" onClick={() => shadowRec("overlap")}>
              ● シャドーイング録音 <Kbd>R</Kbd>
            </button>
            <button className="btn" onClick={() => shadowRec("repeat")}>
              ● リピート録音 <Kbd>⇧R</Kbd>
            </button>
            <button className="btn" onClick={() => playMine()}>
              ▶ 自分の声 <Kbd>P</Kbd>
            </button>
            <button className="btn" onClick={compare}>
              ⇄ 聴き比べ <Kbd>C</Kbd>
            </button>
            <button className="btn" onClick={() => evalRec()}>
              ✦ AI評価 <Kbd>E</Kbd>
            </button>
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <RecMeter owners={["shadow"]} />
          </div>
          {banner && (
            <div className="recording-banner">
              <span className="dot" />
              {banner}
            </div>
          )}
          <div className="hint" style={{ marginTop: 6 }}>
            シャドーイング録音は手本と同時に話します（<b>ヘッドホン推奨</b>）。リピート録音は手本を聴いた後に一人で話します。
          </div>
          <div className="recs">
            {segRecs.length ? (
              segRecs.map((r) => (
                <div
                  key={r.n}
                  className={`recrow${r.n === current?.n ? " sel" : ""}`}
                  onClick={() => setSelRec(r.n)}
                >
                  <span className="t">
                    #{r.n} {r.time}
                  </span>
                  <span>{r.mode === "repeat" ? "リピート" : "シャドーイング"}</span>
                  <Badge v={r.evaluation?.overall} />
                  <span className="sp" />
                  <button
                    className="btn sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      playMine(r);
                    }}
                  >
                    ▶
                  </button>
                  <button
                    className="btn sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      evalRec(r);
                    }}
                  >
                    {r.evaluation ? "結果" : "評価"}
                  </button>
                </div>
              ))
            ) : (
              <div className="hint">まだ録音がありません。R でシャドーイング録音を始めましょう。</div>
            )}
          </div>
          {current && evalBusy[current.n] && (
            <div className="hint" style={{ marginTop: 12 }}>
              <Spinner /> #{current.n} を評価中…
            </div>
          )}
          {current?.evaluation && <EvaluationView n={current.n} ev={current.evaluation} prev={prevEval} />}
        </div>
      )}
    </Panel>
  );
}

function EvaluationView({ n, ev, prev }: { n: number; ev: Evaluation; prev?: Evaluation }) {
  const delta = prev ? ev.overall - prev.overall : null;
  const scores: [number, string][] = [
    [ev.overall, "総合"],
    [ev.pronunciation, "発音"],
    [ev.fluency, "流暢さ"],
    [ev.intonation, "抑揚・リズム"],
    [ev.completeness, "再現度"],
  ];
  return (
    <div style={{ marginTop: 12 }}>
      <div className="row">
        <b>AI評価 #{n}</b>
        {delta != null && (
          <span className="hint">
            前回比 {delta >= 0 ? "+" : ""}
            {delta}
          </span>
        )}
      </div>
      <div className="evalgrid">
        {scores.map(([v, label]) => (
          <div key={label}>
            <b>{v}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <div className="box">{ev.summary_ja}</div>
      <div className="lbl">聞き取られた英文</div>
      <div className="box muted">{ev.heard}</div>
      {ev.improvements_ja?.length > 0 && (
        <>
          <div className="lbl">次に意識すること</div>
          <ul className="tight">
            {ev.improvements_ja.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </>
      )}
      {ev.word_issues?.length > 0 && (
        <>
          <div className="lbl">気になった単語</div>
          {ev.word_issues.map((w, i) => (
            <div className="issue" key={i}>
              <b>{w.word}</b> — {w.problem_ja}
              <br />
              <span className="muted">💡 {w.tip_ja}</span>
            </div>
          ))}
        </>
      )}
      {ev.good_points_ja?.length > 0 && (
        <>
          <div className="lbl">良かった点</div>
          <ul className="tight">
            {ev.good_points_ja.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
