import type { Config, Evaluation, Recording, RecMode, Session, SessionSummary, Tts, Voice } from "./types";

async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof Blob) {
    init.body = body;
    init.headers = { "Content-Type": body.type || "application/octet-stream" };
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(path, init);
  const j = await r.json().catch(() => ({ error: "invalid response" }));
  if (!r.ok) throw new Error(j.error || j.detail || r.statusText);
  return j as T;
}

export const fileUrl = (sid: string, name: string) => `/files/${sid}/${name}`;

export const api = {
  config: () => call<Config>("/api/config"),
  voices: () => call<Voice[]>("/api/voices"),
  sessions: () => call<SessionSummary[]>("/api/sessions"),
  session: (sid: string) => call<Session>(`/api/sessions/${sid}`),
  newSession: (query: string) => call<Session>("/api/sessions", "POST", { query }),
  transcribe: (sid: string, wav: Blob) => call<{ text: string }>(`/api/sessions/${sid}/transcribe`, "POST", wav),
  correct: (sid: string, text: string, level: string, sentences: number) =>
    call<Session>(`/api/sessions/${sid}/correct`, "POST", { text, level, sentences }),
  updateIdeal: (sid: string, ideal: string) => call<Session>(`/api/sessions/${sid}/ideal`, "PUT", { ideal }),
  tts: (sid: string, voiceId: string) => call<Tts>(`/api/sessions/${sid}/tts`, "POST", { voice_id: voiceId || null }),
  addRecording: (sid: string, wav: Blob, seg: string, mode: RecMode, reference: string) =>
    call<Recording>(
      `/api/sessions/${sid}/recordings?` + new URLSearchParams({ seg, mode, reference }),
      "POST",
      wav,
    ),
  evaluate: (sid: string, n: number) => call<Evaluation>(`/api/sessions/${sid}/recordings/${n}/evaluate`, "POST"),
};
