import { useContext, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { HistoryDialog } from "../components/Dialogs";
import { Badge, Chips, Fixes, Kbd, PageBar, Panel, ScoreGrid, Spinner } from "../components/common";
import { useApp } from "../hooks/useApp";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { lastId, rememberLast } from "../lib/last";
import { errMsg } from "../lib/util";
import type { WritingKind, WritingSession } from "../types";

const KINDS: [WritingKind, string][] = [
  ["email", "メール・メッセージ"],
  ["opinion", "意見"],
  ["story", "出来事の説明"],
];

// サーバー（writing.py の word_count）と同じ数え方
const countWords = (t: string) => (t.match(/[A-Za-z0-9']+/g) ?? []).length;

/** ライティング：お題に英文で答える → 添削と観点別の採点 */
export function WritingPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const { settings } = useApp();
  const [session, setSession] = useState<WritingSession | null>(null);
  const [kind, setKind] = useState<WritingKind>("email");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(false);
  const [text, setText] = useState("");
  const [showJa, setShowJa] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // 書き始めた時刻。お題を読んでいる時間は書く速さに含めない
  const startedAt = useRef<number | null>(null);

  useEffect(() => {
    const id = lastId("writing", active);
    if (id) open(id).catch(() => {});
  }, []);

  function reset(s: WritingSession) {
    setSession(s);
    rememberLast("writing", s.id);
    setText(s.submissions.at(-1)?.text ?? "");
    setShowJa(false);
    startedAt.current = null;
  }

  async function open(id: string) {
    reset(await api.writing.get(id));
  }

  async function create() {
    if (loading) return;
    setLoading(true);
    try {
      reset(await api.writing.create(settings.level, kind));
    } catch (e) {
      toast("お題の作成に失敗: " + errMsg(e), true);
    } finally {
      setLoading(false);
    }
  }

  async function submit() {
    if (!session || submitting) return;
    if (!text.trim()) return toast("英文を書いてください");
    setSubmitting(true);
    const seconds = startedAt.current ? (performance.now() - startedAt.current) / 1000 : 0;
    try {
      setSession(await api.writing.submit(session.id, text, seconds));
      // 書き直しの時間は、次に入力し始めたときから測り直す
      startedAt.current = null;
    } catch (e) {
      toast("添削に失敗: " + errMsg(e), true);
    } finally {
      setSubmitting(false);
    }
  }

  useHotkeys({ n: create, N: create });

  const t = session?.task;
  const words = countWords(text);
  const inRange = t ? words >= t.min_words && words <= t.max_words : true;
  const last = session?.submissions.at(-1);

  return (
    <>
      <PageBar newLabel="新しいお題" busy={loading} onNew={create} onHistory={() => setHistory(true)}>
        <select value={kind} onChange={(e) => setKind(e.target.value as WritingKind)}>
          {KINDS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </PageBar>
      <main className="single">
        {!session || !t ? (
          <div className="panel empty-panel">
            <p>お題に英文で答えて、添削と採点を受ける練習です。</p>
            <p className="hint">種類を選んで「新しいお題」を押してください。会話に近い「話すように書く」お題が出ます。</p>
          </div>
        ) : (
          <>
            <Panel n={1} title={t.title}>
              <div className="ideal">{t.task}</div>
              <div className="row" style={{ marginTop: 6 }}>
                <button className="btn sm" onClick={() => setShowJa((v) => !v)}>
                  {showJa ? "訳を隠す" : "日本語訳"}
                </button>
                <span className="hint">
                  {t.min_words}〜{t.max_words} 語
                </span>
              </div>
              {showJa && <div className="box">{t.task_ja}</div>}
              <textarea
                className="editor"
                value={text}
                onChange={(e) => {
                  if (startedAt.current == null) startedAt.current = performance.now();
                  setText(e.target.value);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    submit();
                  }
                }}
                placeholder="ここに英文を書く（辞書や翻訳は使わずに）"
              />
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn primary" onClick={submit} disabled={submitting}>
                  {submitting ? (
                    <>
                      <Spinner /> 添削中
                    </>
                  ) : (
                    <>
                      {last ? "書き直して再提出" : "提出する"} <Kbd>⌘</Kbd>
                      <Kbd>↵</Kbd>
                    </>
                  )}
                </button>
                <span className={inRange ? "hint" : "hint warn"}>{words} 語</span>
              </div>
            </Panel>
            {last && (
              <Panel n={2} title="添削と採点" right={<Badge v={last.grade.overall} />}>
                <ScoreGrid
                  items={[
                    [last.grade.overall, "総合"],
                    [last.grade.cefr, "CEFR"],
                    [last.grade.task, "課題"],
                    [last.grade.grammar, "文法"],
                    [last.grade.vocabulary, "語彙"],
                    [last.grade.coherence, "構成"],
                  ]}
                />
                <div className="box">{last.grade.feedback_ja}</div>
                <div className="lbl">修正ポイント</div>
                <Fixes fixes={last.grade.corrections} />
                <div className="lbl">模範的な書き直し</div>
                <div className="box ideal">{last.grade.improved}</div>
                <div className="lbl">使える表現</div>
                <Chips items={last.grade.key_expressions} />
                {session.submissions.length > 1 && (
                  <>
                    <div className="lbl">提出の履歴</div>
                    <div className="hint">
                      {session.submissions.map((s, i) => (
                        <span key={i}>
                          {i > 0 && " → "}
                          {s.grade.overall} 点（{s.words} 語）
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </Panel>
            )}
          </>
        )}
      </main>
      <HistoryDialog
        skill="writing"
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
