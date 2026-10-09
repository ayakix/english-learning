import { useContext, useEffect, useState } from "react";
import { api } from "../api";
import { Panel } from "../components/common";
import { PageActive } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { errMsg } from "../lib/util";
import type { ProgressWeek, Skill } from "../types";

// 色の順番は dataviz の検証済みパレット（隣り合う系列の色覚多様性の区別を確認済み）。
// 技能と色の対応は固定し、データの有無で塗り替えない
export const SKILLS: { skill: Skill; label: string; color: string }[] = [
  { skill: "speaking", label: "スピーキング", color: "var(--series-1)" },
  { skill: "listening", label: "リスニング", color: "var(--series-2)" },
  { skill: "writing", label: "ライティング", color: "var(--series-3)" },
  { skill: "reading", label: "リーディング", color: "var(--series-4)" },
  { skill: "lesson", label: "教材", color: "var(--series-5)" },
];

const W = 760;
const H = 260;
const PAD = { l: 36, r: 96, t: 12, b: 28 };

/** 進捗：4 技能と教材リスニングの週ごとの平均スコア */
export function ProgressPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const [weeks, setWeeks] = useState<ProgressWeek[] | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  // タブを開くたびに最新の練習結果を読み直す
  useEffect(() => {
    if (active) api.progress().then((p) => setWeeks(p.weeks), (e) => toast("読み込みに失敗: " + errMsg(e), true));
  }, [active]);

  if (!weeks) return <main className="single top" />;
  if (!weeks.length)
    return (
      <main className="single top">
        <div className="panel empty-panel">
          <p>まだスコアがありません。各タブで練習すると、ここに週ごとの推移が出ます。</p>
        </div>
      </main>
    );

  const labels = [...new Set(weeks.map((w) => w.week))].sort();
  const cell = (week: string, skill: Skill) => weeks.find((w) => w.week === week && w.skill === skill);
  const x = (i: number) => PAD.l + (labels.length === 1 ? (W - PAD.l - PAD.r) / 2 : (i * (W - PAD.l - PAD.r)) / (labels.length - 1));
  const y = (v: number) => PAD.t + ((100 - v) * (H - PAD.t - PAD.b)) / 100;

  // 線の終わりのラベルが重ならないよう、近いものを上下にずらす
  const LABEL_GAP = 14;
  const ends = SKILLS.flatMap((s) => {
    const last = labels.map((l, i) => [i, cell(l, s.skill)] as const).filter(([, c]) => c).at(-1);
    return last ? [{ skill: s.skill, y: y(last[1]!.avg) }] : [];
  }).sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) ends[k].y = Math.max(ends[k].y, ends[k - 1].y + LABEL_GAP);
  const labelY = (skill: Skill) => ends.find((e) => e.skill === skill)!.y;

  return (
    <main className="single top">
      <Panel title="週ごとの平均スコア">
        <div className="legend">
          {SKILLS.map((s) => (
            <span key={s.skill}>
              <i style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
        <div className="chart">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="技能ごとの週の平均スコアの推移" onMouseLeave={() => setHover(null)}>
            {[0, 25, 50, 75, 100].map((v) => (
              <g key={v}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="grid" />
                <text x={PAD.l - 6} y={y(v) + 4} className="axis" textAnchor="end">
                  {v}
                </text>
              </g>
            ))}
            {labels.map((l, i) => (
              <text key={l} x={x(i)} y={H - 8} className="axis" textAnchor="middle">
                {l.slice(5)}〜
              </text>
            ))}
            {hover != null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} className="crosshair" />}
            {SKILLS.map((s) => {
              const pts = labels.map((l, i) => [i, cell(l, s.skill)] as const).filter(([, c]) => c);
              if (!pts.length) return null;
              return (
                <g key={s.skill}>
                  <polyline
                    fill="none"
                    stroke={s.color}
                    strokeWidth={2}
                    strokeLinejoin="round"
                    points={pts.map(([i, c]) => `${x(i)},${y(c!.avg)}`).join(" ")}
                  />
                  {pts.map(([i, c]) => (
                    <circle key={i} cx={x(i)} cy={y(c!.avg)} r={5} fill={s.color} className="dot" />
                  ))}
                  {/* 右端に技能名を直接書く（色だけに頼らない）。途中で途切れた系列もプロットの外に置き、線と重ねない */}
                  <text x={W - PAD.r + 10} y={labelY(s.skill) + 4} className="direct">
                    {s.label}
                  </text>
                </g>
              );
            })}
            {/* マーカーより広い当たり判定で、週ごとにツールチップを出す */}
            {labels.map((l, i) => (
              <rect
                key={l}
                x={x(i) - (W - PAD.l - PAD.r) / Math.max(1, labels.length - 1) / 2}
                y={0}
                width={(W - PAD.l - PAD.r) / Math.max(1, labels.length - 1)}
                height={H}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
              />
            ))}
          </svg>
          {hover != null && (
            <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%` }}>
              <b>{labels[hover]} の週</b>
              {SKILLS.map((s) => {
                const c = cell(labels[hover], s.skill);
                return (
                  <div key={s.skill}>
                    <i style={{ background: s.color }} />
                    {s.label}：{c ? `${c.avg}（${c.count} 回）` : "-"}
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <p className="hint">AI の採点は日によってぶれるため、1 回ごとの値ではなく週の平均で傾向を見ます。最終判定は Versant で行います。</p>
      </Panel>

      <Panel title="表">
        <table className="table">
          <thead>
            <tr>
              <th>週</th>
              {SKILLS.map((s) => (
                <th key={s.skill}>{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...labels].reverse().map((l) => (
              <tr key={l}>
                <td>{l}〜</td>
                {SKILLS.map((s) => {
                  const c = cell(l, s.skill);
                  return (
                    <td key={s.skill}>
                      {c ? (
                        <>
                          <b>{c.avg}</b> <span className="muted">（{c.count} 回{c.wpm ? ` / ${c.wpm} wpm` : ""}）</span>
                        </>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </main>
  );
}
