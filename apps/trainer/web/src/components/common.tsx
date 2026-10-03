import { useEffect, useRef, type ReactNode } from "react";
import { recorder, type RecOwner } from "../lib/recorder";
import { fmtTime } from "../lib/util";

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd>{children}</kbd>;
}

export function Spinner() {
  return <span className="spinner" />;
}

export function Panel(props: {
  n?: number;
  title: string;
  right?: ReactNode;
  collapsed?: boolean;
  onToggle?: () => void;
  children: ReactNode;
}) {
  const foldable = !!props.onToggle;
  return (
    <section className={`panel${foldable ? " fold" : ""}${props.collapsed ? " collapsed" : ""}`}>
      <h2
        onClick={(e) => {
          if (!(e.target as HTMLElement).closest("button")) props.onToggle?.();
        }}
      >
        {props.n != null && <span className="n">{props.n}</span>}
        {props.title}
        <span className="sp" />
        {props.right}
      </h2>
      {!props.collapsed && props.children}
    </section>
  );
}

export function Dialog(props: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    if (props.open && !d.open) d.showModal();
    if (!props.open && d.open) d.close();
  }, [props.open]);
  return (
    <dialog
      ref={ref}
      onClose={props.onClose}
      onClick={(e) => {
        // 背景（dialog 自体）をクリックしたら閉じる
        if (e.target === ref.current) props.onClose();
      }}
    >
      <h3>{props.title}</h3>
      {props.open && props.children}
    </dialog>
  );
}

/** 録音中の音量メーターと経過時間。60fps で更新するので React の state を通さず DOM を直接書き換える */
export function RecMeter({ owners }: { owners: RecOwner[] }) {
  const bar = useRef<HTMLElement>(null);
  const timer = useRef<HTMLSpanElement>(null);
  // 呼び出し側は配列リテラルを渡すので、中身で比較して rAF の張り直しを避ける
  const key = owners.join(",");
  useEffect(() => {
    let id = 0;
    const tick = () => {
      const mine = recorder.on && key.split(",").includes(recorder.owner ?? "");
      bar.current!.style.width = (mine ? recorder.level() * 100 : 0) + "%";
      if (mine) timer.current!.textContent = fmtTime(recorder.elapsed());
      id = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(id);
  }, [key]);
  return (
    <>
      <div className="meter">
        <i ref={bar} />
      </div>
      <span className="timer" ref={timer}>
        0:00
      </span>
    </>
  );
}

export function Badge({ v }: { v: number | null | undefined }) {
  if (v == null) return null;
  return <span className={`badge ${v >= 80 ? "g" : v >= 60 ? "y" : "r"}`}>{v}</span>;
}

/** 各ページ上部の「新しい問題」「履歴」ボタン */
export function PageBar(props: {
  newLabel: string;
  busy: boolean;
  busyLabel?: string;
  onNew: () => void;
  onHistory: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="pagebar">
      <button className="btn primary" onClick={props.onNew} disabled={props.busy}>
        {props.busy ? (
          <>
            <Spinner /> {props.busyLabel ?? "作成中"}
          </>
        ) : (
          <>
            {props.newLabel} <Kbd>N</Kbd>
          </>
        )}
      </button>
      {props.children}
      <span className="sp" />
      <button className="btn sm" onClick={props.onHistory}>
        履歴
      </button>
    </div>
  );
}

/** 観点別スコアのタイル */
export function ScoreGrid({ items }: { items: [number | string | null | undefined, string][] }) {
  return (
    <div className="evalgrid" style={{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }}>
      {items.map(([v, label]) => (
        <div key={label}>
          <b>{v ?? "-"}</b>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

/** 添削の修正点（before → after と理由） */
export function Fixes({ fixes }: { fixes: { before: string; after: string; reason_ja: string }[] }) {
  if (!fixes.length) return <div className="muted">大きな修正はありません 🎉</div>;
  return (
    <>
      {fixes.map((f, i) => (
        <div className="fix" key={i}>
          <div>
            <del>{f.before}</del> → <ins>{f.after}</ins>
          </div>
          <div className="why">{f.reason_ja}</div>
        </div>
      ))}
    </>
  );
}

export function Chips({ items }: { items: { en: string; ja: string }[] }) {
  return (
    <div className="chips">
      {items.map((k, i) => (
        <span className="chip" key={i}>
          {k.en}
          <span>{k.ja}</span>
        </span>
      ))}
    </div>
  );
}
