import { useState } from "react";
import type { Correction } from "../types";
import { Chips, Fixes, Panel } from "./common";

export function CorrectionPanel(props: {
  correction: Correction;
  collapsed: boolean;
  onToggle: () => void;
  onSaveIdeal: (ideal: string) => void;
}) {
  const C = props.correction;
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <Panel
      n={2}
      title="添削と理想の文章"
      right={
        <span className="score">
          {C.score ?? "-"}
          <small> / 100</small>
        </span>
      }
      collapsed={props.collapsed}
      onToggle={props.onToggle}
    >
      <div className="box">{C.feedback_ja}</div>
      <div className="lbl">修正ポイント</div>
      <Fixes fixes={C.corrections} />
      <div className="lbl">あなたの文章（最小修正版）</div>
      <div className="box">{C.corrected}</div>
      <div className="lbl">
        理想の文章
        {editing == null && (
          <button className="btn sm" style={{ marginLeft: 6 }} onClick={() => setEditing(C.ideal)}>
            編集
          </button>
        )}
      </div>
      {editing == null ? (
        <div className="box ideal">{C.ideal}</div>
      ) : (
        <div>
          <textarea autoFocus value={editing} onChange={(e) => setEditing(e.target.value)} />
          <div className="row" style={{ marginTop: 6 }}>
            <button
              className="btn sm primary"
              onClick={() => {
                props.onSaveIdeal(editing);
                setEditing(null);
              }}
            >
              保存して音声を作り直す
            </button>
            <button className="btn sm" onClick={() => setEditing(null)}>
              キャンセル
            </button>
          </div>
        </div>
      )}
      <div className="lbl">使える表現</div>
      <Chips items={C.key_expressions} />
    </Panel>
  );
}
