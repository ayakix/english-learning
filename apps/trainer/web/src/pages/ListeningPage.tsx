import { useContext, useEffect, useRef, useState } from "react";
import { api, fileUrl } from "../api";
import { HistoryDialog } from "../components/Dialogs";
import { Badge, Kbd, PageBar, Panel, Spinner } from "../components/common";
import { useApp } from "../hooks/useApp";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { lastId, rememberLast } from "../lib/last";
import { errMsg } from "../lib/util";
import type { DiffToken, ListeningItem, ListeningSession } from "../types";

/** リスニング：ディクテーション（聞いて書き取る） */
export function ListeningPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const { settings } = useApp();
  const [session, setSession] = useState<ListeningSession | null>(null);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [plays, setPlays] = useState<Record<number, number>>({});
  const [checking, setChecking] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    const id = lastId("listening", active);
    if (id) open(id).catch(() => {});
  }, []);

  useEffect(() => {
    if (!active) audio.current?.pause();
  }, [active]);

  function reset(s: ListeningSession) {
    setSession(s);
    rememberLast("listening", s.id);
    setDrafts({});
    setPlays({});
  }

  async function open(id: string) {
    reset(await api.listening.get(id));
  }

  async function create() {
    if (loading) return;
    setLoading(true);
    try {
      reset(await api.listening.create(settings.level, topic, settings.voice));
    } catch (e) {
      toast("問題の作成に失敗: " + errMsg(e), true);
    } finally {
      setLoading(false);
    }
  }

  const current = session?.items.find((it) => it.answer == null);

  function play(it: ListeningItem) {
    if (!session) return;
    const a = audio.current!;
    a.src = fileUrl("listening", session.id, it.file);
    a.play().catch((e) => toast("再生できません: " + errMsg(e), true));
    if (it.answer == null) setPlays((p) => ({ ...p, [it.i]: (p[it.i] ?? 0) + 1 }));
  }

  async function check(it: ListeningItem) {
    if (!session || checking) return;
    const answer = (drafts[it.i] ?? "").trim();
    if (!answer) return toast("聞こえた英文を入力してください");
    setChecking(true);
    try {
      // 1 回目の再生は数えず、「聞き直した回数」として記録する
      setSession(await api.listening.answer(session.id, it.i, answer, Math.max(0, (plays[it.i] ?? 0) - 1)));
    } catch (e) {
      toast("答え合わせに失敗: " + errMsg(e), true);
    } finally {
      setChecking(false);
    }
  }

  useHotkeys({
    n: create,
    N: create,
    Tab: () => current && play(current),
    " ": () => current && play(current),
  });

  const r = session?.result;
  return (
    <>
      <PageBar newLabel="新しいセット" busy={loading} busyLabel="作成中（音声を生成しています）" onNew={create} onHistory={() => setHistory(true)}>
        <input
          className="topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="テーマ（例: restaurant, work meeting。空欄でおまかせ）"
        />
      </PageBar>
      <main className="single">
        {!session ? (
          <div className="panel empty-panel">
            <p>聞こえた英文をそのまま書き取る練習です。</p>
            <p className="hint">「新しいセット」で、レベル（設定）に合った 5 文と音声を作ります。</p>
          </div>
        ) : (
          <Panel
            title={session.title}
            right={
              r?.score != null && (
                <span className="score">
                  {r.score}
                  <small>
                    {" "}
                    / 100（{r.details.answered}/{r.details.total} 問）
                  </small>
                </span>
              )
            }
          >
            <audio ref={audio} preload="auto" />
            <div className="hint" style={{ marginBottom: 8 }}>
              <Kbd>Tab</Kbd> で（入力中でも）もう一度聞く、<Kbd>Enter</Kbd> で答え合わせ。聞き直した回数も記録します。
            </div>
            {session.items.map((it) => (
              <div key={it.i} className={`item${it === current ? " current" : ""}`}>
                <div className="row">
                  <span className="no">{it.i + 1}</span>
                  <button className="btn sm" onClick={() => play(it)} disabled={it.answer == null && it !== current}>
                    ▶ 聞く
                  </button>
                  {it.answer == null ? (
                    plays[it.i] ? <span className="hint">{plays[it.i]} 回再生</span> : null
                  ) : (
                    <>
                      <Badge v={Math.round((it.accuracy ?? 0) * 100)} />
                      <span className="hint">聞き直し {it.replays} 回</span>
                    </>
                  )}
                </div>
                {it === current && (
                  <div className="row" style={{ marginTop: 8 }}>
                    <input
                      className="answer"
                      autoFocus
                      value={drafts[it.i] ?? ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [it.i]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Tab") {
                          e.preventDefault();
                          play(it);
                        }
                        if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                          e.preventDefault();
                          check(it);
                        }
                      }}
                      placeholder="聞こえた英文を入力"
                    />
                    <button className="btn primary" onClick={() => check(it)} disabled={checking}>
                      {checking ? <Spinner /> : "答え合わせ"} <Kbd>↵</Kbd>
                    </button>
                  </div>
                )}
                {it.answer != null && <ItemResult it={it} />}
              </div>
            ))}
            {!current && <div className="box">全問終わりました 🎉 「新しいセット」で次へ。</div>}
          </Panel>
        )}
      </main>
      <HistoryDialog
        skill="listening"
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

function ItemResult({ it }: { it: ListeningItem }) {
  return (
    <div className="item-result">
      <div className="diff">
        {it.diff!.map((d, k) => (
          <DiffWord key={k} d={d} />
        ))}
      </div>
      <div className="muted">{it.text}</div>
      <div className="muted">{it.ja}</div>
      <div className="hint">💡 {it.points_ja}</div>
    </div>
  );
}

function DiffWord({ d }: { d: DiffToken }) {
  if (d.status === "ok") return <span>{d.t} </span>;
  if (d.status === "missing") return <span className="d-missing" title="書き漏れ">{d.t} </span>;
  if (d.status === "extra") return <del title="余計な語">{d.heard} </del>;
  return (
    <span title="聞き間違い">
      <del>{d.heard}</del> <ins>{d.t}</ins>{" "}
    </span>
  );
}
