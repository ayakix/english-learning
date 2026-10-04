import { useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { Kbd, Panel } from "../components/common";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { errMsg } from "../lib/util";
import type { LinkingData, LinkingItem } from "../types";

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
 * 発音：リンキング（音のつながり）の例題を、型ごとに聞いて真似する
 * 例題は Claude が書き、音声は ElevenLabs（米国の声からランダム）で作ってある。
 */
export function PronunciationPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const [data, setData] = useState<LinkingData | null>(null);
  const [type, setType] = useState("");
  const [cur, setCur] = useState(0);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef(new Audio());
  const rows = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    api.linking().then(
      (d) => {
        setData(d);
        setType(d.types[0]?.key ?? "");
      },
      (e) => toast("例題を読み込めません: " + errMsg(e), true),
    );
    const a = audio.current;
    const end = () => setPlaying(null);
    a.addEventListener("ended", end);
    a.addEventListener("pause", end);
    return () => {
      a.removeEventListener("ended", end);
      a.removeEventListener("pause", end);
    };
  }, []);

  useEffect(() => {
    if (!active) audio.current.pause();
  }, [active]);

  const items = data?.items.filter((it) => it.type === type) ?? [];
  const info = data?.types.find((t) => t.key === type);

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
    const n = Math.max(0, Math.min(items.length - 1, i));
    setCur(n);
    rows.current[n]?.scrollIntoView({ block: "nearest" });
  }

  function changeType(key: string) {
    audio.current.pause();
    setType(key);
    setCur(0);
  }

  useHotkeys({
    ArrowDown: () => select(cur + 1),
    ArrowUp: () => select(cur - 1),
    " ": () => items[cur] && play(items[cur], "phrase"),
    Enter: () => items[cur] && play(items[cur], "sentence"),
  });

  return (
    <>
      <div className="pagebar lk-types">
        {data?.types.map((t) => (
          <button key={t.key} className={`btn sm${t.key === type ? " primary" : ""}`} onClick={() => changeType(t.key)}>
            {t.name}
          </button>
        ))}
      </div>
      <main className="single">
        {info && (
          <Panel title={`リンキング：${info.name}`} right={<span className="hint">{items.length} 件</span>}>
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
          </Panel>
        )}
        <div className="lk-list">
          {items.map((it, i) => (
            <div
              key={it.id}
              ref={(el) => {
                rows.current[i] = el;
              }}
              className={`lk-row${i === cur ? " cur" : ""}`}
              onClick={() => setCur(i)}
            >
              <div className="lk-head">
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
                <span className="sp" />
                <span className="hint">{it.voice?.name}</span>
              </div>
              <div className="lk-head">
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
          ))}
        </div>
      </main>
    </>
  );
}
