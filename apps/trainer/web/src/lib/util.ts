export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));
