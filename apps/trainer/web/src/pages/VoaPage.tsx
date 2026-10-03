import { useContext, useEffect, useRef, useState } from "react";
import { api, fileUrl } from "../api";
import { HistoryDialog } from "../components/Dialogs";
import { Badge, Kbd, PageBar, Panel, ScoreGrid, Spinner } from "../components/common";
import { useApp } from "../hooks/useApp";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { lastId, rememberLast } from "../lib/last";
import { errMsg, fmtTime } from "../lib/util";
import type { Question, VoaDictation, VoaSession, VoaSource, VoaZone } from "../types";
import { DiffWord } from "./ListeningPage";

const RATES = [1, 1.25, 1.5];

/**
 * 教材リスニング：記事と音声で 聞く → 書き取る → 読む を通す
 * 取得元は VOA（実際の記事）と AI 教材（Claude の原稿 + ElevenLabs の音声）から選べる。
 * 先に本文を読むと聞き取りの練習にならないので、本文は「読む」の段階まで表示しない（サーバーも返さない）。
 */
export function VoaPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const { settings, updateSettings } = useApp();
  const [session, setSession] = useState<VoaSession | null>(null);
  const [zones, setZones] = useState<Record<VoaSource, VoaZone[]>>({ voa: [], ai: [] });
  const [src, setSrc] = useState<VoaSource>("ai");
  const [zone, setZone] = useState("all");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(false);
  const [busy, setBusy] = useState(false);
  // 聞く
  const [lisAnswers, setLisAnswers] = useState<(number | null)[]>([]);
  const [fullPlays, setFullPlays] = useState(0);
  const [playing, setPlaying] = useState(false);
  // 書き取る
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [clipPlays, setClipPlays] = useState<Record<number, number>>({});
  // 読む
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [readSec, setReadSec] = useState<number | null>(null);
  const [rdAnswers, setRdAnswers] = useState<(number | null)[]>([]);

  const audio = useRef<HTMLAudioElement>(null);
  const clipEnd = useRef<number | null>(null);
  const pos = useRef<HTMLSpanElement>(null);
  const timer = useRef<HTMLSpanElement>(null);
  const rate = settings.voaRate;

  useEffect(() => {
    loadZones();
    const id = lastId("voa", active);
    if (id) open(id).catch(() => {});
  }, []);

  useEffect(() => {
    if (!active) audio.current?.pause();
  }, [active]);

  useEffect(() => {
    if (audio.current) audio.current.playbackRate = rate;
  }, [rate, session?.id]);

  // 再生位置の表示と、書き取りの区間の終わりで止める処理。
  // timeupdate は 4 回/秒ほどしか来ず区間の終わりを越えてしまうので、rAF で見る
  useEffect(() => {
    let id = 0;
    const tick = () => {
      const a = audio.current;
      if (a) {
        if (clipEnd.current != null && a.currentTime >= clipEnd.current) {
          a.pause();
          clipEnd.current = null;
        }
        if (pos.current) pos.current.textContent = `${fmtTime(a.currentTime)} / ${fmtTime(a.duration || 0)}`;
      }
      id = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(id);
  }, []);

  // 読んでいる間の経過時間の表示
  useEffect(() => {
    if (startedAt == null || readSec != null) return;
    const id = setInterval(() => {
      if (timer.current) timer.current.textContent = fmtTime((performance.now() - startedAt) / 1000);
    }, 500);
    return () => clearInterval(id);
  }, [startedAt, readSec]);

  function loadZones() {
    api.voa.zones().then(setZones, () => {});
  }

  function reset(s: VoaSession) {
    audio.current?.pause();
    setSession(s);
    rememberLast("voa", s.id);
    setLisAnswers(s.listening.questions.map(() => null));
    setFullPlays(0);
    setDrafts({});
    setClipPlays({});
    setStartedAt(null);
    setReadSec(null);
    setRdAnswers(s.reading.questions.map(() => null));
  }

  async function open(id: string) {
    reset(await api.voa.get(id));
  }

  async function create() {
    if (loading) return;
    setLoading(true);
    try {
      reset(await api.voa.create(src, zone));
      loadZones();
    } catch (e) {
      toast("記事の準備に失敗: " + errMsg(e), true);
    } finally {
      setLoading(false);
    }
  }

  // 送信して、返ってきた session で画面を更新する（各段階の提出で共通）
  async function send(fn: () => Promise<VoaSession>) {
    if (busy) return;
    setBusy(true);
    try {
      setSession(await fn());
    } catch (e) {
      toast("送信に失敗: " + errMsg(e), true);
    } finally {
      setBusy(false);
    }
  }

  const stage = session?.stage;

  function toggleFull() {
    const a = audio.current;
    if (!a || !session) return;
    clipEnd.current = null;
    if (!a.paused) return a.pause();
    // 最後まで聞いた後・最初からの再生を「1 回聞いた」と数える
    if (a.ended || a.currentTime < 0.5) {
      a.currentTime = 0;
      if (stage === "listening") setFullPlays((n) => n + 1);
    }
    a.play().catch((e) => toast("再生できません: " + errMsg(e), true));
  }

  function seek(delta: number) {
    const a = audio.current;
    if (a) a.currentTime = Math.max(0, a.currentTime + delta);
  }

  function playClip(d: VoaDictation) {
    const a = audio.current;
    if (!a) return;
    a.currentTime = d.start;
    clipEnd.current = d.end;
    a.play().catch((e) => toast("再生できません: " + errMsg(e), true));
    if (d.answer == null) setClipPlays((p) => ({ ...p, [d.i]: (p[d.i] ?? 0) + 1 }));
  }

  function changeRate(step: number) {
    const i = Math.min(RATES.length - 1, Math.max(0, RATES.indexOf(rate) + step));
    updateSettings({ voaRate: RATES[i] });
  }

  const currentClip = stage === "dictation" ? session!.dictation.find((d) => d.answer == null) : undefined;

  function submitListening() {
    if (!session) return;
    if (lisAnswers.some((a) => a == null)) return toast("すべての設問に答えてください");
    audio.current?.pause();
    send(() => api.voa.listening(session.id, lisAnswers as number[], fullPlays));
  }

  function submitClip(d: VoaDictation) {
    if (!session) return;
    const answer = (drafts[d.i] ?? "").trim();
    if (!answer) return toast("聞こえた英文を入力してください");
    send(() => api.voa.dictation(session.id, d.i, answer, clipPlays[d.i] ?? 0));
  }

  function submitReading() {
    if (!session || readSec == null) return;
    if (rdAnswers.some((a) => a == null)) return toast("すべての設問に答えてください");
    send(() => api.voa.reading(session.id, rdAnswers as number[], readSec));
  }

  const readPhase = stage !== "reading" ? null : startedAt == null ? "ready" : readSec == null ? "reading" : "answering";

  function advanceReading() {
    if (readPhase === "ready") setStartedAt(performance.now());
    else if (readPhase === "reading") setReadSec((performance.now() - startedAt!) / 1000);
  }

  useHotkeys({
    n: create,
    N: create,
    " ": () => (stage === "reading" && readPhase !== "answering" ? advanceReading() : toggleFull()),
    ArrowLeft: () => seek(-5),
    ArrowRight: () => seek(5),
    "[": () => changeRate(-1),
    "]": () => changeRate(1),
    Tab: () => currentClip && playClip(currentClip),
  });

  const r = session?.result;
  return (
    <>
      <PageBar
        newLabel="新しい記事"
        busy={loading}
        busyLabel={src === "voa" ? "記事を探して問題を作成中（30 秒ほど）" : "準備中"}
        onNew={create}
        onHistory={() => setHistory(true)}
      >
        <select
          value={src}
          onChange={(e) => {
            setSrc(e.target.value as VoaSource);
            setZone("all");
          }}
          title="取得元"
        >
          <option value="ai">AI 教材（約 1 分半）</option>
          <option value="voa">VOA（約 5 分）</option>
        </select>
        <select value={zone} onChange={(e) => setZone(e.target.value)} title={src === "voa" ? "セクション" : "分野"}>
          <option value="all">{src === "voa" ? "すべてのセクション" : "すべての分野"}</option>
          {zones[src].map((z) => (
            <option key={z.key} value={z.key} disabled={z.left === 0}>
              {z.name}
              {z.left != null && `（残り ${z.left}）`}
            </option>
          ))}
        </select>
      </PageBar>
      <main className="single">
        {!session ? (
          <div className="panel empty-panel">
            <p>記事と音声で、聞く → 書き取る → 読む を順に練習します。</p>
            <p className="hint">
              AI 教材は、Claude が書いた原稿と ElevenLabs の音声（時計・ワイン・航空・アプリ開発・ランニング・子育て・自然科学・金融）です。
              VOA は、VOA の記者が書いた記事（パブリックドメイン）を選び、設問を作ります。
            </p>
          </div>
        ) : (
          <>
            <audio
              ref={audio}
              preload="auto"
              src={fileUrl("voa", session.id, "audio.mp3")}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onLoadedMetadata={(e) => (e.currentTarget.playbackRate = rate)}
            />
            <div className="player panel">
              <button className="btn primary" onClick={toggleFull}>
                {playing && clipEnd.current == null ? "❚❚ 一時停止" : "▶ 全体を再生"} <Kbd>Space</Kbd>
              </button>
              <button className="btn sm" onClick={() => seek(-5)} title="5 秒戻る">
                ← 5s
              </button>
              <button className="btn sm" onClick={() => seek(5)} title="5 秒進む">
                5s →
              </button>
              <span className="timer" ref={pos}>
                0:00
              </span>
              <span className="sp" />
              <span className="hint">速度</span>
              {RATES.map((v) => (
                <button key={v} className={`btn sm${v === rate ? " on" : ""}`} onClick={() => updateSettings({ voaRate: v })}>
                  {v}x
                </button>
              ))}
              <span className="hint">
                <Kbd>[</Kbd> <Kbd>]</Kbd>
              </span>
            </div>

            <Panel
              n={1}
              title="聞く：本文を見ずに全体を聞いて答える"
              right={
                <span className="hint">
                  {session.words} 語・{fmtTime(session.duration)}・{session.audio_wpm} wpm
                  {stage === "listening" && fullPlays > 0 && ` ・ ${fullPlays} 回目`}
                </span>
              }
            >
              <div className="hint" style={{ marginBottom: 6 }}>
                「{session.title}」
              </div>
              <Quiz
                questions={session.listening.questions}
                mine={session.listening.answers ?? lisAnswers}
                done={session.listening.answers != null}
                onPick={(qi, oi) => setLisAnswers((a) => a.map((v, k) => (k === qi ? oi : v)))}
              />
              {stage === "listening" ? (
                <button className="btn primary" onClick={submitListening} disabled={busy}>
                  {busy ? <Spinner /> : "答え合わせ"}
                </button>
              ) : (
                <div className="box">
                  <b>
                    正解 {session.listening.correct} / {session.listening.questions.length}
                  </b>
                  （全体を {session.listening.plays} 回再生）
                  <div className="muted" style={{ marginTop: 4 }}>
                    {session.summary_ja}
                  </div>
                </div>
              )}
            </Panel>

            {stage !== "listening" && (
              <Panel n={2} title="書き取る：音声から切り出した文">
                <div className="hint" style={{ marginBottom: 8 }}>
                  <Kbd>Tab</Kbd> で（入力中でも）文を再生、<Kbd>Enter</Kbd> で答え合わせ。聞いた回数も記録します。
                </div>
                {session.dictation.map((d) => (
                  <div key={d.i} className={`item${d === currentClip ? " current" : ""}`}>
                    <div className="row">
                      <span className="no">{d.i + 1}</span>
                      <button className="btn sm" onClick={() => playClip(d)} disabled={d.answer == null && d !== currentClip}>
                        ▶ 聞く
                      </button>
                      {d.answer == null ? (
                        clipPlays[d.i] ? <span className="hint">{clipPlays[d.i]} 回再生</span> : null
                      ) : (
                        <>
                          <Badge v={Math.round((d.accuracy ?? 0) * 100)} />
                          <span className="hint">{d.plays} 回再生</span>
                        </>
                      )}
                    </div>
                    {d === currentClip && (
                      <div className="row" style={{ marginTop: 8 }}>
                        <input
                          className="answer"
                          autoFocus
                          value={drafts[d.i] ?? ""}
                          onChange={(e) => setDrafts((x) => ({ ...x, [d.i]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Tab") {
                              e.preventDefault();
                              playClip(d);
                            }
                            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                              e.preventDefault();
                              submitClip(d);
                            }
                          }}
                          placeholder="聞こえた英文を入力"
                        />
                        <button className="btn primary" onClick={() => submitClip(d)} disabled={busy}>
                          {busy ? <Spinner /> : "答え合わせ"} <Kbd>↵</Kbd>
                        </button>
                      </div>
                    )}
                    {d.answer != null && (
                      <div className="item-result">
                        <div className="diff">
                          {d.diff!.map((t, k) => (
                            <DiffWord key={k} d={t} />
                          ))}
                        </div>
                        <div className="muted">{d.text}</div>
                        <div className="muted">{d.ja}</div>
                        <div className="hint">💡 {d.points_ja}</div>
                      </div>
                    )}
                  </div>
                ))}
              </Panel>
            )}

            {(stage === "reading" || stage === "done") && (
              <Panel
                n={3}
                title="読む：本文を読んで答える"
                right={
                  <span className="hint">
                    {readPhase === "reading" && <span className="timer" ref={timer}>0:00</span>}
                    {readPhase === "answering" && fmtTime(readSec!)}
                  </span>
                }
              >
                {readPhase === "ready" ? (
                  <div className="row">
                    <button className="btn primary" onClick={advanceReading}>
                      読み始める <Kbd>Space</Kbd>
                    </button>
                    <span className="hint">押すと本文が表示され、読む時間を計り始めます。</span>
                  </div>
                ) : (
                  <>
                    <div className="passage">
                      {session.paragraphs.map((p, i) => (p.heading ? <h4 key={i}>{p.text}</h4> : <p key={i}>{p.text}</p>))}
                    </div>
                    {readPhase === "reading" && (
                      <button className="btn primary" onClick={advanceReading}>
                        読み終えた <Kbd>Space</Kbd>
                      </button>
                    )}
                  </>
                )}
                {(readPhase === "answering" || stage === "done") && (
                  <>
                    <div className="lbl">設問</div>
                    <Quiz
                      questions={session.reading.questions}
                      mine={session.reading.answers ?? rdAnswers}
                      done={stage === "done"}
                      onPick={(qi, oi) => setRdAnswers((a) => a.map((v, k) => (k === qi ? oi : v)))}
                    />
                    {stage === "reading" && (
                      <button className="btn primary" onClick={submitReading} disabled={busy}>
                        {busy ? <Spinner /> : "提出する"}
                      </button>
                    )}
                  </>
                )}
              </Panel>
            )}

            {stage === "done" && (
              <Panel n={4} title="結果">
                <ScoreGrid
                  items={[
                    [r?.score, "スコア"],
                    [`${session.listening.correct} / ${session.listening.questions.length}`, "聞く"],
                    [r?.details.dictation != null ? `${r.details.dictation}%` : null, "書き取り"],
                    [`${session.reading.correct} / ${session.reading.questions.length}`, "読む"],
                    [session.reading.wpm, "WPM"],
                  ]}
                />
                <div className="hint">スコアは「聞く」の正答率と「書き取り」の一致率の平均です。</div>
                {session.glossary.length > 0 && (
                  <>
                    <div className="lbl">{session.source.stock_id ? "この話の用語" : "Words in This Story"}</div>
                    <dl className="glossary">
                      {/* AI 教材は用語だけ（定義なし）なので、dd が空でも崩れないようにしている */}
                      {session.glossary.map((g, i) => (
                        <div key={i}>
                          <dt>{g.word}</dt>
                          <dd>{g.definition}</dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
              </Panel>
            )}

            <div className="credit">
              出典：
              {session.source.url ? (
                <a href={session.source.url} target="_blank" rel="noreferrer">
                  {session.source.site}「{session.source.title}」
                </a>
              ) : (
                <>
                  {session.source.site}「{session.source.title}」
                </>
              )}
              （{session.source.published}）{stage === "done" && <> — {session.source.credit}</>}
            </div>
          </>
        )}
      </main>
      <HistoryDialog
        skill="voa"
        open={history}
        onClose={() => setHistory(false)}
        onPick={(id) => {
          setHistory(false);
          open(id).catch((e) => toast("読み込みに失敗: " + errMsg(e), true));
        }}
      />
    </>
  );
}

/** 4 択の設問。done になると正解・不正解と解説を出す */
function Quiz(props: {
  questions: Question[];
  mine: (number | null)[];
  done: boolean;
  onPick: (qi: number, oi: number) => void;
}) {
  return (
    <>
      {props.questions.map((q, qi) => (
        <div className="question" key={qi}>
          <div className="q">
            {qi + 1}. {q.q}
            {props.done && (q.answer === props.mine[qi] ? " ⭕️" : " ❌")}
          </div>
          {q.options.map((o, oi) => (
            <label
              key={oi}
              className={`option${props.done && oi === q.answer ? " correct" : ""}${props.done && oi === props.mine[qi] && oi !== q.answer ? " wrong" : ""}`}
            >
              <input
                type="radio"
                name={`voa-${q.q}`}
                checked={props.mine[qi] === oi}
                disabled={props.done}
                onChange={() => props.onPick(qi, oi)}
              />
              {o}
            </label>
          ))}
          {props.done && <div className="why">{q.explanation_ja}</div>}
        </div>
      ))}
    </>
  );
}
