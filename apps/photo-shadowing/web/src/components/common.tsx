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
