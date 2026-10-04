import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Kbd, Panel } from "../components/common";
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

// 今日の範囲の先頭（絞り込んだ一覧の何番目か）を、モード・レベルごとに覚えておく。
// 練習ログが残らないタブなので、次の範囲を探さずに再開できるようにするため
const RANGE_KEY = "trainer:versant:start";

function loadStarts(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(RANGE_KEY) || "{}");
  } catch {
    return {};
  }
}

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
  const [starts, setStarts] = useState<Record<string, number>>(loadStarts);
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
  const rangeKey = (m: Mode, lv: string) => `${m}:${m === "repeats" ? lv : "all"}`;
  // 一覧が短くなっても範囲が外に出ないように、件数で丸める
  const start = items.length ? (starts[rangeKey(mode, level)] ?? 0) % items.length : 0;
  const end = Math.min(start + DAILY[mode], items.length);
  const inRange = (i: number) => i >= start && i < end;

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
    const n = items.length;
    // 最後まで行ったら先頭に戻る（言えるようになるまで繰り返すため）
    let next: number;
    if (dir === 1) next = end >= n ? 0 : end;
    else next = start === 0 ? Math.floor((n - 1) / DAILY[mode]) * DAILY[mode] : Math.max(0, start - DAILY[mode]);
    const all = { ...starts, [rangeKey(mode, level)]: next };
    setStarts(all);
    try {
      localStorage.setItem(RANGE_KEY, JSON.stringify(all));
    } catch {
      // 保存できなくても、その場の範囲としては使える
    }
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
          {items.length > 0 && (
            <div className="vs-today">
              <div>
                <b>今日の範囲</b>：{start + 1}〜{end} 番（{items[start].id}〜{items[end - 1].id}）
                <span className="vs-count">
                  {inRange(cur) ? `${cur - start + 1} / ${end - start}` : `範囲外（${cur + 1} 番）`}
                </span>
              </div>
              <div className="vs-bar">
                <div style={{ width: `${inRange(cur) ? ((cur - start + 1) / (end - start)) * 100 : 0}%` }} />
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button className="btn sm" onClick={() => moveRange(-1)}>
                  ◀ 前の範囲
                </button>
                <button className="btn sm primary" onClick={() => moveRange(1)}>
                  終わったら次の範囲へ ▶
                </button>
              </div>
            </div>
          )}
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
                  <span className="vs-num">{i + 1}</span>
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
                  <span className="hint">
                    {it.id} · {mode === "repeats" && `${it.words} 語 · `}
                    {it.voice?.name}
                  </span>
                </div>
                {visible && mode === "short-answers" && (
                  <div className="hint" style={{ paddingLeft: 44 }}>
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
