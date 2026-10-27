export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// ハッシュの後ろの値（#versant?repeats=rp141 の repeats）。Claude が今日の範囲を付けて開くため
export const hashParam = (name: string) => new URLSearchParams(location.hash.split("?")[1] ?? "").get(name);

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));
