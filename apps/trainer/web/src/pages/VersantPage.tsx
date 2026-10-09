import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Kbd, Panel, TodayRange } from "../components/common";
import { useDailyRange } from "../hooks/useDailyRange";
import { useDrillAudio } from "../hooks/useDrillAudio";
import { useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { errMsg } from "../lib/util";
import type { DrillData, DrillItem } from "../types";

type Mode = "repeats" | "short-answers";

const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: "repeats", label: "復唱", hint: "音声を聞いて、聞こえたとおりにそのまま繰り返します（Versant の Repeats）。" },
  {
    key: "short-answers",
    label: "即答",
    hint: "質問を聞いて、1〜2 語ですぐに答えます（Versant の Short Answer Questions）。",
  },
];

// 1 日の量（curriculum/roadmap.md の「1 日・1 週間の型」）
const DAILY: Record<Mode, number> = { repeats: 20, "short-answers": 15 };


/**
 * Versant 形式のドリル：復唱と即答
 * 例文・質問は Claude が書き、音声は ElevenLabs（採用済みの声からランダム）で作ってある。
 * 文字を見ると聞き取りの練習にならないので、テキストは最初は隠し、押したら見せる。
 */
export function VersantPage() {
  const toast = useToast();
  const [mode, setMode] = useState<Mode>("repeats");
  const [data, setData] = useState<Partial<Record<Mode, DrillData>>>({});
  const [level, setLevel] = useState<string>("all");
  const [showAll, setShowAll] = useState(false);
  const [shown, setShown] = useState<Set<string>>(new Set());
  const [cur, setCur] = useState(0);
  const rows = useRef<(HTMLDivElement | null)[]>([]);
  const { playing, play, stop } = useDrillAudio();

  useEffect(() => {
    if (data[mode]) return;
    api.drill(mode).then(
      (d) => setData((prev) => ({ ...prev, [mode]: d })),
      (e) => toast("例題を読み込めません: " + errMsg(e), true),
    );
  }, [mode]);

  const d = data[mode];
  const items = (d?.items ?? []).filter((it) => mode !== "repeats" || level === "all" || String(it.level) === level);
  const info = MODES.find((m) => m.key === mode)!;
  // 範囲はモード・レベルごとに覚えておく（レベルで絞ると番号が変わるため）
  const range = useDailyRange("trainer:versant:start", `${mode}:${mode === "repeats" ? level : "all"}`, DAILY[mode], items.length);
  const { start, inRange } = range;

  // 開いたときは今日の範囲の先頭を選ぶ
  useEffect(() => {
    if (!items.length) return;
    setCur(start);
    rows.current[start]?.scrollIntoView({ block: "nearest" });
  }, [mode, level, items.length]);

  function change(next: { mode?: Mode; level?: string }) {
    stop();
    if (next.mode) setMode(next.mode);
    if (next.level) setLevel(next.level);
  }

  function moveRange(dir: 1 | -1) {
    const next = range.move(dir);
    stop();
    setCur(next);
    rows.current[next]?.scrollIntoView({ block: "start" });
  }

  function playItem(it: DrillItem) {
    play(`/api/drills/${mode}/audio/${it.id}/${it.audio.main.file}`, it.id);
  }

  function reveal(id: string) {
    setShown((prev) => new Set(prev).add(id));
  }

  function select(i: number) {
    const n = Math.max(0, Math.min(items.length - 1, i));
    setCur(n);
    rows.current[n]?.scrollIntoView({ block: "nearest" });
  }

  useHotkeys({
    ArrowDown: () => select(cur + 1),
    ArrowUp: () => select(cur - 1),
    " ": () => items[cur] && playItem(items[cur]),
    v: () => items[cur] && reveal(items[cur].id),
  });

  return (
    <>
      <div className="pagebar lk-types">
        {MODES.map((m) => (
          <button key={m.key} className={`btn${m.key === mode ? " primary" : ""}`} onClick={() => change({ mode: m.key })}>
            {m.label}
          </button>
        ))}
      </div>
      <main className="single">
        <Panel
          title={`Versant：${info.label}`}
          right={
            <label className="hint row" style={{ gap: 6 }}>
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              テキストをすべて表示
            </label>
          }
        >
          <div className="hint">{info.hint}</div>
          {mode === "repeats" && d?.levels && (
            <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
              {[["all", "すべて"], ...Object.entries(d.levels)].map(([k, label]) => (
                <button key={k} className={`btn sm${k === level ? " primary" : ""}`} onClick={() => change({ level: k })}>
                  {k === "all" ? label : `レベル ${k}（${label}）`}
                </button>
              ))}
            </div>
          )}
          <div className="hint" style={{ marginTop: 8 }}>
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> で選び、<Kbd>Space</Kbd> で再生、<Kbd>V</Kbd> でテキストを表示します。{items.length} 件
          </div>
          <TodayRange range={range} cur={cur} ids={items.map((it) => it.id)} onMove={moveRange} />
        </Panel>
        <div className="lk-list">
          {items.map((it, i) => {
            const visible = showAll || shown.has(it.id);
            return (
              <div
                key={it.id}
                ref={(el) => {
                  rows.current[i] = el;
                }}
                className={`lk-row${i === cur ? " cur" : ""}${inRange(i) ? " today" : ""}`}
                onClick={() => setCur(i)}
              >
                <div className="lk-head">
                  <span className="vs-num">{it.id}</span>
                  <button
                    className={`btn sm${playing === it.id ? " primary" : ""}`}
                    onClick={() => playItem(it)}
                    title="再生"
                  >
                    ▶
                  </button>
                  {visible ? (
                    <span className="lk-sentence">{mode === "repeats" ? it.text : it.question}</span>
                  ) : (
                    <button className="btn sm ghost" onClick={() => reveal(it.id)}>
                      テキストを表示
                    </button>
                  )}
                  <span className="sp" />
                  {mode === "repeats" && <span className="hint">{it.words} 語</span>}
                </div>
                {visible && mode === "short-answers" && (
                  <div className="hint" style={{ paddingLeft: 59 }}>
                    答え：<b>{it.answers?.[0]}</b>
                    {it.answers && it.answers.length > 1 && `（ほかに ${it.answers.slice(1).join(" / ")}）`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </main>
    </>
  );
}
