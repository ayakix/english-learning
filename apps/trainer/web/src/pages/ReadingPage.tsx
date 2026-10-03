import { useContext, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { HistoryDialog } from "../components/Dialogs";
import { Chips, Kbd, PageBar, Panel, ScoreGrid, Spinner } from "../components/common";
import { useApp } from "../hooks/useApp";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { lastId, rememberLast } from "../lib/last";
import { errMsg, fmtTime } from "../lib/util";
import type { ReadingSession } from "../types";

/**
 * リーディング：読む → 設問に答える
 * 読む速さを測るため、「読み始める」を押すまで本文を隠し、「読み終えた」までの時間を計る。
 */
export function ReadingPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const { settings } = useApp();
  const [session, setSession] = useState<ReadingSession | null>(null);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [readSec, setReadSec] = useState<number | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const timer = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const id = lastId("reading", active);
    if (id) open(id).catch(() => {});
  }, []);

  // 読んでいる間の経過時間の表示
  useEffect(() => {
    if (startedAt == null || readSec != null) return;
    const id = setInterval(() => {
      if (timer.current) timer.current.textContent = fmtTime((performance.now() - startedAt) / 1000);
    }, 500);
    return () => clearInterval(id);
  }, [startedAt, readSec]);

  function reset(s: ReadingSession) {
    setSession(s);
    rememberLast("reading", s.id);
    setStartedAt(null);
    setReadSec(null);
    setAnswers(s.questions.map(() => null));
  }

  async function open(id: string) {
    reset(await api.reading.get(id));
  }

  async function create() {
    if (loading) return;
    setLoading(true);
    try {
      reset(await api.reading.create(settings.level, topic));
    } catch (e) {
      toast("文章の作成に失敗: " + errMsg(e), true);
    } finally {
      setLoading(false);
    }
  }

  async function submit() {
    if (!session || submitting || readSec == null) return;
    if (answers.some((a) => a == null)) return toast("すべての設問に答えてください");
    setSubmitting(true);
    try {
      setSession(await api.reading.submit(session.id, answers as number[], readSec));
    } catch (e) {
      toast("提出に失敗: " + errMsg(e), true);
    } finally {
      setSubmitting(false);
    }
  }

  const sub = session?.submission;
  const phase = !session ? "none" : sub ? "done" : startedAt == null ? "ready" : readSec == null ? "reading" : "answering";

  function advance() {
    if (phase === "ready") setStartedAt(performance.now());
    else if (phase === "reading") setReadSec((performance.now() - startedAt!) / 1000);
  }

  useHotkeys({ n: create, N: create, " ": advance });

  return (
    <>
      <PageBar newLabel="新しい文章" busy={loading} onNew={create} onHistory={() => setHistory(true)}>
        <input
          className="topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="テーマ（例: travel, technology。空欄でおまかせ）"
        />
      </PageBar>
      <main className="single">
        {!session ? (
          <div className="panel empty-panel">
            <p>文章を読んで設問に答える練習です。正答率と読む速さ（WPM）を記録します。</p>
            <p className="hint">「新しい文章」で、レベル（設定）に合った文章と設問を作ります。</p>
          </div>
        ) : (
          <>
            <Panel
              n={1}
              title={session.title}
              right={
                <span className="hint">
                  {session.words} 語{phase === "reading" && <> ・ <span className="timer" ref={timer}>0:00</span></>}
                  {readSec != null && !sub && ` ・ ${fmtTime(readSec)}`}
                </span>
              }
            >
              {phase === "ready" ? (
                <div className="row">
                  <button className="btn primary" onClick={advance}>
                    読み始める <Kbd>Space</Kbd>
                  </button>
                  <span className="hint">押すと本文が表示され、読む時間を計り始めます。</span>
                </div>
              ) : (
                <>
                  <div className="passage">
                    {session.passage.split(/\n\s*\n/).map((p, i) => (
                      <p key={i}>{p}</p>
                    ))}
                  </div>
                  {phase === "reading" && (
                    <button className="btn primary" onClick={advance}>
                      読み終えた <Kbd>Space</Kbd>
                    </button>
                  )}
                </>
              )}
            </Panel>
            {(phase === "answering" || phase === "done") && (
              <Panel n={2} title="設問">
                {sub && (
                  <ScoreGrid
                    items={[
                      [`${sub.correct} / ${session.questions.length}`, "正解"],
                      [sub.wpm, "WPM"],
                      [fmtTime(sub.reading_seconds), "読んだ時間"],
                    ]}
                  />
                )}
                {session.questions.map((q, qi) => {
                  const mine = sub ? sub.answers[qi] : answers[qi];
                  return (
                    <div className="question" key={qi}>
                      <div className="q">
                        {qi + 1}. {q.q}
                        {sub && (q.answer === mine ? " ⭕️" : " ❌")}
                      </div>
                      {q.options.map((o, oi) => (
                        <label
                          key={oi}
                          className={`option${sub && oi === q.answer ? " correct" : ""}${sub && oi === mine && oi !== q.answer ? " wrong" : ""}`}
                        >
                          <input
                            type="radio"
                            name={`q${qi}`}
                            checked={mine === oi}
                            disabled={!!sub}
                            onChange={() => setAnswers((a) => a.map((v, k) => (k === qi ? oi : v)))}
                          />
                          {o}
                        </label>
                      ))}
                      {sub && <div className="why">{q.explanation_ja}</div>}
                    </div>
                  );
                })}
                {!sub && (
                  <button className="btn primary" onClick={submit} disabled={submitting}>
                    {submitting ? <Spinner /> : "提出する"}
                  </button>
                )}
                {sub && session.glossary.length > 0 && (
                  <>
                    <div className="lbl">語彙</div>
                    <Chips items={session.glossary} />
                  </>
                )}
              </Panel>
            )}
          </>
        )}
      </main>
      <HistoryDialog
        skill="reading"
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
