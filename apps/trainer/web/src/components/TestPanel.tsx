import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { recorder } from "../lib/recorder";
import { errMsg } from "../lib/util";
import type { Session } from "../types";
import { Kbd, Panel, RecMeter, ScoreGrid, Spinner } from "./common";

type Phase = "ready" | "prep" | "speak" | "grading" | "done";

/**
 * スピーキングテスト（TOEIC Speaking の写真描写と同じ形式）
 * 準備 45 秒 → 解答 30 秒を自動で進め、録音を Gemini が採点する。
 * 本番と同じく、途中で止めたりやり直したりはできない（時間内に話す練習のため）。
 */
export function TestPanel(props: {
  session: Session;
  echo: boolean;
  onStart: () => void;
  onBeforeRecord: () => void;
  onGraded: (s: Session) => void;
}) {
  const toast = useToast();
  const t = props.session.test!;
  const [phase, setPhase] = useState<Phase>(t.grade ? "done" : "ready");
  const [left, setLeft] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    setPhase(props.session.test?.grade ? "done" : "ready");
    return stopTimer;
  }, [props.session.id]);

  function stopTimer() {
    if (timer.current != null) clearInterval(timer.current);
    timer.current = null;
  }

  // 終了時刻から残り秒数を計算する（setInterval の遅れが積み重ならないように）
  function countdown(seconds: number, onEnd: () => void) {
    stopTimer();
    const end = performance.now() + seconds * 1000;
    setLeft(seconds);
    timer.current = window.setInterval(() => {
      const rest = Math.max(0, Math.ceil((end - performance.now()) / 1000));
      setLeft(rest);
      if (rest <= 0) {
        stopTimer();
        onEnd();
      }
    }, 200);
  }

  async function start() {
    if (phase !== "ready") return;
    props.onBeforeRecord();
    try {
      // マイクの許可を準備時間の前に済ませておく（解答の開始が遅れないように）
      await recorder.init(props.echo);
    } catch (e) {
      return toast("マイクを使用できません: " + errMsg(e), true);
    }
    props.onStart();
    setPhase("prep");
    recorder.beep();
    countdown(t.prep, speak);
  }

  async function speak() {
    recorder.beep();
    await recorder.start(props.echo, "test");
    setPhase("speak");
    countdown(t.response, finish);
  }

  async function finish() {
    stopTimer();
    if (!recorder.isOwner("test")) return;
    const { blob, seconds } = recorder.stop();
    recorder.beep();
    setPhase("grading");
    try {
      props.onGraded(await api.speaking.submitTest(props.session.id, blob, seconds));
      setPhase("done");
    } catch (e) {
      toast("採点に失敗: " + errMsg(e), true);
      setPhase("ready");
    }
  }

  // 採点後は Space をシャドーイングの再生に使うので、テスト中だけ登録する
  useHotkeys(phase === "ready" ? { " ": start } : phase === "speak" ? { " ": finish } : {});

  const g = t.grade;
  return (
    <Panel
      n={1}
      title="スピーキングテスト（写真描写）"
      right={g && <span className="score">{g.score}<small> / 100</small></span>}
    >
      {phase === "ready" && (
        <>
          <div className="hint" style={{ marginBottom: 8 }}>
            TOEIC Speaking と同じ形式です。準備 {t.prep} 秒のあと、合図の音で {t.response} 秒間の録音が始まります。
            写真の場所、中心の人や物、周りの様子を英語で説明してください。
          </div>
          <button className="btn primary" onClick={start}>
            テストを始める <Kbd>Space</Kbd>
          </button>
        </>
      )}
      {(phase === "prep" || phase === "speak") && (
        <div className={`test-timer ${phase}`}>
          <div className="label">{phase === "prep" ? "準備時間" : "解答時間（録音中）"}</div>
          <div className="sec">{left}</div>
          <div className="bar">
            <i style={{ width: `${(left / (phase === "prep" ? t.prep : t.response)) * 100}%` }} />
          </div>
          {phase === "speak" && (
            <div className="row" style={{ justifyContent: "center", marginTop: 8 }}>
              <RecMeter owners={["test"]} />
              <button className="btn sm" onClick={finish}>
                早めに終える <Kbd>Space</Kbd>
              </button>
            </div>
          )}
        </div>
      )}
      {phase === "grading" && (
        <div className="row">
          <Spinner /> 文字起こしと採点をしています…
        </div>
      )}
      {phase === "done" && g && (
        <>
          <ScoreGrid
            items={[
              [`${g.toeic} / 3`, "TOEIC 基準"],
              [g.content, "内容"],
              [g.grammar, "文法"],
              [g.vocabulary, "語彙"],
              [g.delivery, "話し方"],
            ]}
          />
          <div className="lbl">あなたの解答（{Math.round(t.seconds ?? 0)} 秒）</div>
          <div className="box">{t.answer || "（聞き取れませんでした）"}</div>
          <div className="hint">下の「添削と理想の文章」に修正点と模範解答、その下で模範解答の音声でシャドーイングできます。</div>
        </>
      )}
    </Panel>
  );
}
