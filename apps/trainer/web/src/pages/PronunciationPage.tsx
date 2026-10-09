import { useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { Kbd, Panel, TodayRange } from "../components/common";
import { useDailyRange } from "../hooks/useDailyRange";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { errMsg } from "../lib/util";
import { useDrillAudio } from "../hooks/useDrillAudio";
import type { DrillData, DrillItem, LinkingData, LinkingItem } from "../types";

/** つなぎ記号（‿）と、発音されない音（括弧の中）を色分けして表示する */
function Marked({ text }: { text: string }) {
  const parts = text.split(/(‿|\([^)]*\))/).filter(Boolean);
  return (
    <>
      {parts.map((p, i) =>
        p === "‿" ? (
          <span key={i} className="lk-link">‿</span>
        ) : p.startsWith("(") ? (
          <span key={i} className="lk-drop">{p.slice(1, -1)}</span>
        ) : (
          p
        ),
      )}
    </>
  );
}

/** 例文の中のフレーズ部分を強調する。‿ でつながった語のまとまりか、1 語の例はその語を探す */
function Sentence({ item }: { item: LinkingItem }) {
  const s = item.sentence;
  const re = s.includes("‿")
    ? /[A-Za-z']+(?:‿[A-Za-z']+)+/g
    : new RegExp(item.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of s.matchAll(re)) {
    out.push(s.slice(last, m.index));
    out.push(
      <mark key={m.index} className="lk-target">
        <Marked text={m[0]} />
      </mark>,
    );
    last = m.index! + m[0].length;
  }
  out.push(s.slice(last));
  return <>{out}</>;
}

/**
 * 発音：リンキング（音のつながり）とミニマルペアを切り替えて練習する
 * 例題は Claude が書き、音声は ElevenLabs（米国の声からランダム）で作ってある。
 */
export function PronunciationPage() {
  const [mode, setMode] = useState<"linking" | "pairs">("linking");
  return (
    <>
      <div className="pagebar lk-types">
        {(
          [
            ["linking", "リンキング"],
            ["pairs", "ミニマルペア"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} className={`btn${k === mode ? " primary" : ""}`} onClick={() => setMode(k)}>
            {label}
          </button>
        ))}
      </div>
      {mode === "linking" ? <LinkingView /> : <MinimalPairsView />}
    </>
  );
}

// 1 日の量：リンキングは 1 型（25 例）を 2 日で回す（curriculum/roadmap.md の「1 日・1 週間の型」）
const LINKING_DAILY = 13;
// 型は 2 日ずつ順に進めるので、次に開いたときも前回の型から始められるように覚えておく
const TYPE_KEY = "trainer:linking:type";

function loadType(): string | null {
  try {
    return localStorage.getItem(TYPE_KEY);
  } catch {
    return null;
  }
}

/** リンキングの例題を、型ごとに聞いて真似する */
function LinkingView() {
  const toast = useToast();
  const active = useContext(PageActive);
  const [data, setData] = useState<LinkingData | null>(null);
  const [type, setType] = useState("");
  const [cur, setCur] = useState(0);
  const [playing, setPlaying] = useState<string | null>(null);
  // 既定は今日の範囲だけを出す（25 例が並ぶと、今日やる所を探す手間がかかるため）
  const [showAll, setShowAll] = useState(false);
  const audio = useRef(new Audio());
  const rows = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    api.linking().then(
      (d) => {
        setData(d);
        const saved = loadType();
        setType(saved && d.types.some((t) => t.key === saved) ? saved : (d.types[0]?.key ?? ""));
      },
      (e) => toast("例題を読み込めません: " + errMsg(e), true),
    );
    const a = audio.current;
    const end = () => setPlaying(null);
    a.addEventListener("ended", end);
    a.addEventListener("pause", end);
    return () => {
      // ミニマルペアに切り替えると画面ごと外れるので、再生中の音を止める
      a.pause();
      a.removeEventListener("ended", end);
      a.removeEventListener("pause", end);
    };
  }, []);

  useEffect(() => {
    if (!active) audio.current.pause();
  }, [active]);

  const items = data?.items.filter((it) => it.type === type) ?? [];
  const info = data?.types.find((t) => t.key === type);
  const range = useDailyRange("trainer:linking:start", type, LINKING_DAILY, items.length);

  // 開いたとき・型を替えたときは今日の範囲の先頭を選ぶ
  useEffect(() => {
    if (!items.length) return;
    setCur(range.start);
    rows.current[range.start]?.scrollIntoView({ block: "nearest" });
  }, [type, items.length]);

  function moveRange(dir: 1 | -1) {
    const next = range.move(dir);
    audio.current.pause();
    setCur(next);
    rows.current[next]?.scrollIntoView({ block: "start" });
  }

  function play(it: LinkingItem, which: "phrase" | "sentence") {
    const a = audio.current;
    const key = `${it.id}:${which}`;
    // 再生中のものをもう一度押したら止める
    if (playing === key) return a.pause();
    a.src = `/api/linking/audio/${it.id}/${which === "phrase" ? it.audio : it.audio_sentence}`;
    a.play().then(
      () => setPlaying(key),
      (e) => toast("再生できません: " + errMsg(e), true),
    );
  }

  function select(i: number) {
    // 今日の範囲だけを出しているときは、↑↓ も範囲の中で動かす
    const [lo, hi] = showAll ? [0, items.length - 1] : [range.start, range.end - 1];
    const n = Math.max(lo, Math.min(hi, i));
    setCur(n);
    rows.current[n]?.scrollIntoView({ block: "nearest" });
  }

  function changeType(key: string) {
    audio.current.pause();
    setType(key);
    try {
      localStorage.setItem(TYPE_KEY, key);
    } catch {
      // 保存できなくても、その場で型は切り替えられる
    }
  }

  useHotkeys({
    ArrowDown: () => select(cur + 1),
    ArrowUp: () => select(cur - 1),
    " ": () => items[cur] && play(items[cur], "phrase"),
    Enter: () => items[cur] && play(items[cur], "sentence"),
  });

  return (
    <>
      <div className="pagebar lk-types sub">
        {data?.types.map((t) => (
          <button key={t.key} className={`btn sm${t.key === type ? " primary" : ""}`} onClick={() => changeType(t.key)}>
            {t.name}
          </button>
        ))}
      </div>
      <main className="single">
        {info && (
          <Panel
            title={`リンキング：${info.name}`}
            right={
              <label className="hint row" style={{ gap: 6 }}>
                <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
                全 {items.length} 件を表示
              </label>
            }
          >
            <div className="hint">{info.description_ja}</div>
            <div className="box lk-example">
              例：<Marked text={info.example} />
            </div>
            <div className="hint">
              <span className="lk-link">‿</span> はつながる所、<span className="lk-drop">薄い文字</span>
              はほとんど聞こえない音です。カタカナは聞こえ方の目安です。
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> で選び、<Kbd>Space</Kbd> でフレーズ、<Kbd>Enter</Kbd> で例文を再生します。
            </div>
            <TodayRange range={range} cur={cur} ids={items.map((it) => it.id)} onMove={moveRange} />
          </Panel>
        )}
        <div className="lk-list">
          {items.map((it, i) =>
            !showAll && !range.inRange(i) ? null : (
              <div
                key={it.id}
                ref={(el) => {
                  rows.current[i] = el;
                }}
                className={`lk-row${i === cur ? " cur" : ""}${range.inRange(i) ? " today" : ""}`}
                onClick={() => setCur(i)}
              >
                <div className="lk-head">
                  <span className="vs-num">{it.id}</span>
                  <button
                    className={`btn sm${playing === `${it.id}:phrase` ? " primary" : ""}`}
                    onClick={() => play(it, "phrase")}
                    title="フレーズを再生"
                  >
                    ▶
                  </button>
                  <span className="lk-phrase">
                    <Marked text={it.phrase} />
                  </span>
                  <span className="lk-kana">{it.kana}</span>
                </div>
                <div className="lk-head">
                  <span className="vs-num" />
                  <button
                    className={`btn sm${playing === `${it.id}:sentence` ? " primary" : ""}`}
                    onClick={() => play(it, "sentence")}
                    title="例文を再生"
                  >
                    ▶
                  </button>
                  <span className="lk-sentence">
                    <Sentence item={it} />
                  </span>
                </div>
              </div>
            ),
          )}
        </div>
      </main>
    </>
  );
}

/**
 * ミニマルペア：1 音だけ違う 2 語（light / right など）を聞き比べ、言い分ける
 * 日本人が区別しにくい子音・母音の組を 8 つ用意している。
 */
function MinimalPairsView() {
  const toast = useToast();
  const [data, setData] = useState<DrillData | null>(null);
  const [type, setType] = useState("");
  const [cur, setCur] = useState(0);
  const rows = useRef<(HTMLDivElement | null)[]>([]);
  const { playing, play, stop } = useDrillAudio();

  useEffect(() => {
    api.drill("minimal-pairs").then(
      (d) => {
        setData(d);
        setType(d.types?.[0]?.key ?? "");
      },
      (e) => toast("例題を読み込めません: " + errMsg(e), true),
    );
  }, []);

  const items = data?.items.filter((it) => it.type === type) ?? [];
  const info = data?.types?.find((t) => t.key === type);

  function playWord(it: DrillItem, slot: "a" | "b") {
    play(`/api/drills/minimal-pairs/audio/${it.id}/${it.audio[slot].file}`, `${it.id}:${slot}`);
  }

  function select(i: number) {
    const n = Math.max(0, Math.min(items.length - 1, i));
    setCur(n);
    rows.current[n]?.scrollIntoView({ block: "nearest" });
  }

  useHotkeys({
    ArrowDown: () => select(cur + 1),
    ArrowUp: () => select(cur - 1),
    ArrowLeft: () => items[cur] && playWord(items[cur], "a"),
    ArrowRight: () => items[cur] && playWord(items[cur], "b"),
  });

  return (
    <>
      <div className="pagebar lk-types sub">
        {data?.types?.map((t) => (
          <button
            key={t.key}
            className={`btn sm${t.key === type ? " primary" : ""}`}
            onClick={() => {
              stop();
              setType(t.key);
              setCur(0);
            }}
          >
            {t.name}
          </button>
        ))}
      </div>
      <main className="single">
        {info && (
          <Panel title={`ミニマルペア：${info.name}`} right={<span className="hint">{items.length} 組</span>}>
            <div className="hint">{info.description_ja}</div>
            <div className="hint" style={{ marginTop: 6 }}>
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> で選び、<Kbd>←</Kbd> で左、<Kbd>→</Kbd> で右の単語を再生します。
            </div>
          </Panel>
        )}
        <div className="mp-grid">
          {items.map((it, i) => (
            <div
              key={it.id}
              ref={(el) => {
                rows.current[i] = el;
              }}
              className={`lk-row mp-row${i === cur ? " cur" : ""}`}
              onClick={() => setCur(i)}
            >
              <span className="vs-num">{it.id}</span>
              {(["a", "b"] as const).map((slot) => (
                <button
                  key={slot}
                  className={`btn mp-word${playing === `${it.id}:${slot}` ? " primary" : ""}`}
                  onClick={() => playWord(it, slot)}
                >
                  ▶ {it[slot]}
                </button>
              ))}
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
