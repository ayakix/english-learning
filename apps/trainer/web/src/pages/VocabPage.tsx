import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Kbd, Panel } from "../components/common";
import { useDrillAudio } from "../hooks/useDrillAudio";
import { useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { errMsg } from "../lib/util";
import type { VocabData, VocabItem, VocabMode as Mode, VocabReviewItem } from "../types";

const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: "en-ja", label: "英→日", hint: "英単語を見て、日本語の意味を言います。" },
  { key: "ja-en", label: "日→英", hint: "日本語を見て、英単語を言います（意味は分かるのに英語が出てこない語を減らす）。" },
];

// 向きとテーマは、Claude が「今日は日→英の台所」のように指示するので、次に開いたときも同じ所から始められるように覚える
const MODE_KEY = "trainer:vocab:mode";
const THEME_KEY = "trainer:vocab:theme";
// テーマの代わりに選ぶ「振り返り」。× だった語と review.json の語を向きごとに API が集める
const REVIEW = "review";

function loadPref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // 保存できなくても、その場では切り替えられる
  }
}

/** 身近なものの単語：テーマごとに 20 語。意味（答え）は最初は隠し、押したら見せる */
export function VocabPage() {
  const toast = useToast();
  const [data, setData] = useState<VocabData | null>(null);
  const [mode, setMode] = useState<Mode>(() => (loadPref(MODE_KEY) === "ja-en" ? "ja-en" : "en-ja"));
  const [theme, setTheme] = useState<string>(() => loadPref(THEME_KEY) ?? "");
  const [review, setReview] = useState<VocabReviewItem[]>([]);
  const [shown, setShown] = useState<Set<string>>(new Set());
  // 今日この向きで付けた ○/×（ID → 言えたか）
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const [cur, setCur] = useState(0);
  const rows = useRef<(HTMLDivElement | null)[]>([]);
  const { playing, play, stop } = useDrillAudio();

  useEffect(() => {
    api.vocab.get().then(
      (d) => {
        setData(d);
        setTheme((t) => (t === REVIEW || d.themes.some((th) => th.key === t) ? t : (d.themes[0]?.key ?? "")));
      },
      (e) => toast("単語を読み込めません: " + errMsg(e), true),
    );
  }, []);

  useEffect(() => {
    setMarks({});
    api.vocab.marks(mode).then(
      (r) => setMarks(r.marks),
      (e) => toast("記録を読み込めません: " + errMsg(e), true),
    );
  }, [mode]);

  // 振り返りは開いたときの一覧を保つ（○ を付けた途端に行が消えて、次の語の位置がずれないように）。向きを替えたら取り直す
  useEffect(() => {
    if (theme !== REVIEW) return;
    setReview([]);
    api.vocab.review(mode).then(
      (r) => setReview(r.items),
      (e) => toast("振り返りを読み込めません: " + errMsg(e), true),
    );
  }, [mode, theme]);

  const items: VocabItem[] = theme === REVIEW ? review : (data?.items.filter((it) => it.theme === theme) ?? []);
  const reasons = new Map(review.map((it) => [it.id, it.reason]));
  const info = MODES.find((m) => m.key === mode)!;

  // 向き・テーマを替えたら、答えを隠し直して先頭から始める
  useEffect(() => {
    stop();
    setShown(new Set());
    setCur(0);
    rows.current[0]?.scrollIntoView({ block: "nearest" });
  }, [mode, theme]);

  function changeMode(m: Mode) {
    setMode(m);
    savePref(MODE_KEY, m);
  }

  function changeTheme(t: string) {
    setTheme(t);
    savePref(THEME_KEY, t);
  }

  /**
   * 単語の音声（ElevenLabs）を再生する。
   * 単語は綴りから読み方を覚え違えやすい（oven を「オーブン」と覚えて「アヴン」が聞き取れない）ので、発音を確かめられるようにする
   */
  function speak(it: VocabItem) {
    if (!it.audio_file) return toast("この単語の音声はまだありません", true);
    play(`/api/drills/vocab/audio/${it.id}/${it.audio_file}`, it.id);
  }

  function toggle(id: string) {
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
    // 押してすぐ次の語に進めるよう、先に画面へ反映し、保存の結果で置き換える
    setMarks((prev) => ({ ...prev, [it.id]: ok }));
    api.vocab.mark(mode, it.id, ok).then(
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
    " ": () => items[cur] && speak(items[cur]),
    Enter: () => items[cur] && toggle(items[cur].id),
    // 付けたら次の語へ進む（1 語 1 キーで済むように）
    o: () => {
      mark(cur, true);
      select(cur + 1);
    },
    x: () => {
      mark(cur, false);
      select(cur + 1);
    },
  });

  const prompt = (it: VocabItem) => (mode === "en-ja" ? it.en : it.ja);
  const answer = (it: VocabItem) => (mode === "en-ja" ? it.ja : it.en);

  return (
    <>
      <div className="pagebar lk-types">
        {MODES.map((m) => (
          <button key={m.key} className={`btn${m.key === mode ? " primary" : ""}`} onClick={() => changeMode(m.key)}>
            {m.label}
          </button>
        ))}
      </div>
      <div className="pagebar lk-types sub">
        <button className={`btn sm${theme === REVIEW ? " primary" : ""}`} onClick={() => changeTheme(REVIEW)}>
          振り返り
        </button>
        {data?.themes.map((t) => (
          <button key={t.key} className={`btn sm${t.key === theme ? " primary" : ""}`} onClick={() => changeTheme(t.key)}>
            {t.name}
          </button>
        ))}
      </div>
      <main className="single">
        <Panel title={`単語：${info.label}`}>
          <div className="hint">{info.hint}</div>
          <div className="hint" style={{ marginTop: 8 }}>
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>（<Kbd>k</Kbd>
            <Kbd>j</Kbd>）で選び、<Kbd>Space</Kbd> で英語を再生、<Kbd>Enter</Kbd> で答えを表示・非表示、<Kbd>O</Kbd>
            で言えた（○）、<Kbd>X</Kbd> で言えなかった（×）を付けます。{items.length} 語
          </div>
          {theme === REVIEW && (
            <div className="hint" style={{ marginTop: 8 }}>
              この向きで最後に × を付けた語と、復習に指定した語です。○ を付けると次に開いたとき外れます。
            </div>
          )}
          <div className="hint" style={{ marginTop: 8 }}>
            今日の記録：<b className="vs-ok">○ {okCount}</b> / <b className="vs-ng">× {ngCount}</b>
          </div>
        </Panel>
        <div className="lk-list">
          {items.map((it, i) => {
            const visible = shown.has(it.id);
            return (
              <div
                key={it.id}
                ref={(el) => {
                  rows.current[i] = el;
                }}
                className={`lk-row${i === cur ? " cur" : ""}`}
                onClick={() => setCur(i)}
              >
                <div className="lk-head">
                  <span className="vs-num">{it.id}</span>
                  {theme === REVIEW && <span className="hint">{reasons.get(it.id)}</span>}
                  <button
                    className={`btn sm${playing === it.id ? " primary" : ""}`}
                    onClick={() => speak(it)}
                    disabled={!it.audio_file}
                    title="英語を再生"
                  >
                    ▶
                  </button>
                  <b className="lk-sentence">{prompt(it)}</b>
                  {visible ? (
                    <span className="lk-sentence">{answer(it)}</span>
                  ) : (
                    <button className="btn sm ghost" onClick={() => toggle(it.id)}>
                      答えを表示
                    </button>
                  )}
                  <span className="sp" />
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
                {visible && (
                  <div className="hint" style={{ paddingLeft: 59 }}>
                    {it.example}
                    {it.note && `（${it.note}）`}
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
