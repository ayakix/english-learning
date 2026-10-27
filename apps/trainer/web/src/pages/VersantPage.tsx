import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Kbd, Panel, TodayRange } from "../components/common";
import { useDailyRange } from "../hooks/useDailyRange";
import { useDrillAudio } from "../hooks/useDrillAudio";
import { useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { errMsg, hashParam } from "../lib/util";
import type { DrillData, DrillItem, VersantMode as Mode } from "../types";

const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: "repeats", label: "復唱", hint: "音声を聞いて、聞こえたとおりにそのまま繰り返します（Versant の Repeats）。" },
  {
    key: "short-answers",
    label: "即答",
    hint: "質問を聞いて、1〜2 語ですぐに答えます（Versant の Short Answer Questions）。",
  },
  {
    key: "review",
    label: "振り返り",
    hint: "間違えた復唱・即答だけをやり直します。一覧は Claude が × の付いたものから書き換えます。",
  },
];

// 1 日の量（curriculum/roadmap.md の「1 日・1 週間の型」）。振り返りは一覧そのものが今日の範囲
const DAILY: Record<Mode, number> = { repeats: 20, "short-answers": 15, review: 0 };


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
  // 今日このモードで付けた ○/×（ID → 言えたか）
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const [cur, setCur] = useState(0);
  const rows = useRef<(HTMLDivElement | null)[]>([]);
  // URL で指定された範囲を当てたモード・レベル。一度だけ当て、そのあとは「次の範囲へ」で進めた位置を使う
  const jumped = useRef<Set<string>>(new Set());
  const { playing, play, stop } = useDrillAudio();

  useEffect(() => {
    // 振り返りの一覧は Claude が書き換えるので、開くたびに読み直す
    if (data[mode] && mode !== "review") return;
    (mode === "review" ? api.review() : api.drill(mode)).then(
      (d) => setData((prev) => ({ ...prev, [mode]: d })),
      (e) => toast("例題を読み込めません: " + errMsg(e), true),
    );
  }, [mode]);

  useEffect(() => {
    setMarks({});
    api.versant.marks(mode).then(
      (r) => setMarks(r.marks),
      (e) => toast("記録を読み込めません: " + errMsg(e), true),
    );
  }, [mode]);

  // 振り返りでは復唱と即答が混ざるので、例題ごとの種類で表示を変える
  const kindOf = (it: DrillItem) => it.kind ?? mode;

  const d = data[mode];
  const items = (d?.items ?? []).filter((it) => mode !== "repeats" || level === "all" || String(it.level) === level);
  const info = MODES.find((m) => m.key === mode)!;
  // 範囲はモード・レベルごとに覚えておく（レベルで絞ると番号が変わるため）
  const rangeKey = `${mode}:${mode === "repeats" ? level : "all"}`;
  const range = useDailyRange("trainer:versant:start", rangeKey, DAILY[mode], items.length);
  const { inRange } = range;

  // 開いたときは今日の範囲の先頭を選ぶ。URL に先頭の ID（#versant?repeats=rp141）があれば、そこを先頭にする
  useEffect(() => {
    if (!items.length) return;
    let first = range.start;
    const i = items.findIndex((it) => it.id === hashParam(mode));
    if (i >= 0 && !jumped.current.has(rangeKey)) {
      jumped.current.add(rangeKey);
      range.jump(i);
      first = i;
    }
    setCur(first);
    rows.current[first]?.scrollIntoView({ block: "nearest" });
  }, [mode, level, items.length]);

  function change(next: { mode?: Mode; level?: string }) {
    stop();
    if (next.mode) {
      setMode(next.mode);
      // 表示済みの印は ID で持つので、即答で見た問題が振り返りでも見えてしまう。モードを替えたら隠し直す
      setShown(new Set());
    }
    if (next.level) setLevel(next.level);
  }

  function moveRange(dir: 1 | -1) {
    const next = range.move(dir);
    stop();
    setCur(next);
    rows.current[next]?.scrollIntoView({ block: "start" });
  }

  function playItem(it: DrillItem) {
    play(`/api/drills/${kindOf(it)}/audio/${it.id}/${it.audio.main.file}`, it.id);
  }

  // 表示したあと、もう一度テキストを見ずに言い直せるように、隠すこともできる
  function toggleText(id: string) {
    setShown((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  function select(i: number) {
    const n = Math.max(0, Math.min(items.length - 1, i));
    setCur(n);
    rows.current[n]?.scrollIntoView({ block: "nearest" });
  }

  function mark(i: number, ok: boolean) {
    const it = items[i];
    if (!it) return;
    // 押してすぐ次の文に進めるよう、先に画面へ反映し、保存の結果で置き換える
    setMarks((prev) => ({ ...prev, [it.id]: ok }));
    api.versant.mark(mode, it.id, ok).then(
      (r) => setMarks(r.marks),
      (e) => toast("記録できません: " + errMsg(e), true),
    );
  }

  const okCount = Object.values(marks).filter(Boolean).length;
  const ngCount = Object.values(marks).length - okCount;

  useHotkeys({
    ArrowDown: () => select(cur + 1),
    ArrowUp: () => select(cur - 1),
    // Vim と同じ j / k でも動かす（ホームポジションから手を離さずに済むように）
    j: () => select(cur + 1),
    k: () => select(cur - 1),
    " ": () => items[cur] && playItem(items[cur]),
    Enter: () => items[cur] && toggleText(items[cur].id),
    // 付けたら次の文へ進む（1 文 1 キーで済むように）
    o: () => {
      mark(cur, true);
      select(cur + 1);
    },
    x: () => {
      mark(cur, false);
      select(cur + 1);
    },
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
            <Kbd>↓</Kbd>（<Kbd>k</Kbd>
            <Kbd>j</Kbd>）で選び、<Kbd>Space</Kbd> で再生、<Kbd>Enter</Kbd> でテキストを表示・非表示、<Kbd>O</Kbd> で言えた（○）、<Kbd>X</Kbd>
            で言えなかった（×）を付けます。{items.length} 件
            {mode === "review" && d?.updated && `（${d.updated} 更新）`}
          </div>
          <div className="hint" style={{ marginTop: 8 }}>
            今日の記録：<b className="vs-ok">○ {okCount}</b> / <b className="vs-ng">× {ngCount}</b>
          </div>
          {mode !== "review" && (
            <TodayRange range={range} cur={cur} ids={items.map((it) => it.id)} onMove={moveRange} />
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
                className={`lk-row${i === cur ? " cur" : ""}${mode !== "review" && inRange(i) ? " today" : ""}`}
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
                    <span className="lk-sentence">{kindOf(it) === "repeats" ? it.text : it.question}</span>
                  ) : (
                    <button className="btn sm ghost" onClick={() => toggleText(it.id)}>
                      テキストを表示
                    </button>
                  )}
                  <span className="sp" />
                  {kindOf(it) === "repeats" && <span className="hint">{it.words} 語</span>}
                  {/* スマホではキーが使えないので、押して付けられるボタンも置く */}
                  <button
                    className={`btn sm${marks[it.id] === true ? " vs-ok-on" : ""}`}
                    onClick={() => mark(i, true)}
                    title="言えた"
                  >
                    ○
                  </button>
                  <button
                    className={`btn sm${marks[it.id] === false ? " vs-ng-on" : ""}`}
                    onClick={() => mark(i, false)}
                    title="言えなかった"
                  >
                    ×
                  </button>
                </div>
                {visible && kindOf(it) === "short-answers" && (
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
