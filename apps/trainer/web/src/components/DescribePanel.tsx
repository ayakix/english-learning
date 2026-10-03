import { useState, type Dispatch, type SetStateAction } from "react";
import { api } from "../api";
import { useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { recorder } from "../lib/recorder";
import { errMsg } from "../lib/util";
import type { Session } from "../types";
import { Kbd, Panel, RecMeter, Spinner } from "./common";

export function DescribePanel(props: {
  session: Session | null;
  text: string;
  onText: Dispatch<SetStateAction<string>>;
  echo: boolean;
  collapsed: boolean;
  onToggle: () => void;
  onExpand: () => void;
  onBeforeRecord: () => void;
  onCorrect: () => void;
  correcting: boolean;
}) {
  const toast = useToast();
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const s = props.session;

  async function toggleMic() {
    if (!s) return toast("先に写真を表示してください（N）");
    if (transcribing) return;
    if (recorder.on && recorder.owner === "desc") {
      setRecording(false);
      const { blob, seconds } = recorder.stop();
      if (seconds < 0.6) return toast("録音が短すぎます");
      setTranscribing(true);
      try {
        const r = await api.speaking.transcribe(s.id, blob);
        // 何回かに分けて話せるよう、既存の文に追記する
        // 文字起こしを待つ間に手で直した内容を消さないよう、最新の値に追記する
        props.onText((cur) => (cur.trim() ? cur.trim() + " " : "") + r.text.trim());
        toast("文字起こししました。⌘Enter で添削");
      } catch (e) {
        toast("文字起こし失敗: " + errMsg(e), true);
      } finally {
        setTranscribing(false);
      }
      return;
    }
    if (recorder.on) return;
    props.onBeforeRecord();
    try {
      await recorder.start(props.echo, "desc");
    } catch (e) {
      return toast("マイクを使用できません: " + errMsg(e), true);
    }
    props.onExpand();
    setRecording(true);
  }

  useHotkeys({ m: toggleMic, M: toggleMic });

  const last = s?.attempts.at(-1);
  return (
    <Panel
      n={1}
      title="英語で説明する"
      right={<span className="hint">写真を見て、思いつくまま話してみましょう</span>}
      collapsed={props.collapsed}
      onToggle={props.onToggle}
    >
      <div className="row">
        <button className={`btn ${recording ? "rec" : "primary"}`} onClick={toggleMic} disabled={transcribing}>
          {transcribing ? (
            <>
              <Spinner /> 文字起こし中
            </>
          ) : (
            <>
              🎙 話す <Kbd>M</Kbd>
            </>
          )}
        </button>
        <RecMeter owners={["desc"]} />
      </div>
      {recording && (
        <div className="recording-banner">
          <span className="dot" />
          録音中… もう一度 <Kbd>M</Kbd> で停止して文字起こし
        </div>
      )}
      <div style={{ marginTop: 10 }}>
        <textarea
          value={props.text}
          onChange={(e) => props.onText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              props.onCorrect();
            }
            if (e.key === "Escape") e.currentTarget.blur();
          }}
          placeholder="ここに文字起こしが入ります（手で直してもOK）"
        />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn primary" onClick={props.onCorrect} disabled={props.correcting}>
          {props.correcting ? (
            <>
              <Spinner /> 添削中
            </>
          ) : (
            <>
              添削する <Kbd>⌘</Kbd>
              <Kbd>↵</Kbd>
            </>
          )}
        </button>
        {last && (
          <span className="hint">
            これまで {s!.attempts.length} 回提出（前回 {last.score ?? "-"} 点）
          </span>
        )}
      </div>
    </Panel>
  );
}
