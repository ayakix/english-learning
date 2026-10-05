import { useState } from "react";

function load(storeKey: string): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(storeKey) || "{}");
  } catch {
    return {};
  }
}

/**
 * 一覧を 1 日の量（size 件）で区切った「今日の範囲」
 * 範囲の先頭（一覧の何番目か）を rangeKey ごとに覚えておく。
 * 発音・Versant は練習ログが残らないタブなので、次の範囲を探さずに再開できるようにするため
 */
export function useDailyRange(storeKey: string, rangeKey: string, size: number, total: number) {
  const [starts, setStarts] = useState<Record<string, number>>(() => load(storeKey));
  // 一覧が短くなっても範囲が外に出ないように、件数で丸める
  const start = total ? (starts[rangeKey] ?? 0) % total : 0;
  const end = Math.min(start + size, total);

  /** 範囲を前後に動かし、新しい先頭を返す */
  function move(dir: 1 | -1): number {
    let next: number;
    // 最後まで行ったら先頭に戻る（言えるようになるまで繰り返すため）
    if (dir === 1) next = end >= total ? 0 : end;
    else next = start === 0 ? Math.floor((total - 1) / size) * size : Math.max(0, start - size);
    const all = { ...starts, [rangeKey]: next };
    setStarts(all);
    try {
      localStorage.setItem(storeKey, JSON.stringify(all));
    } catch {
      // 保存できなくても、その場の範囲としては使える
    }
    return next;
  }

  return { start, end, inRange: (i: number) => i >= start && i < end, move };
}

export type DailyRange = ReturnType<typeof useDailyRange>;
