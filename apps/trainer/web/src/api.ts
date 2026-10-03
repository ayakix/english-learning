import type {
  Config,
  Evaluation,
  ListeningSession,
  ProgressPoint,
  ProgressWeek,
  ReadingSession,
  Recording,
  RecMode,
  Session,
  SessionSummary,
  Skill,
  Tts,
  Voice,
  VoaSession,
  VoaSource,
  VoaZone,
  WritingKind,
  WritingSession,
} from "./types";

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

export const fileUrl = (skill: Skill, sid: string, name: string) => `/files/${skill}/${sid}/${name}`;

const sp = (sid: string) => `/api/speaking/sessions/${sid}`;

export const api = {
  config: () => call<Config>("/api/config"),
  voices: () => call<Voice[]>("/api/voices"),
  sessions: (skill: Skill) => call<SessionSummary[]>(`/api/${skill}/sessions`),
  progress: () => call<{ points: ProgressPoint[]; weeks: ProgressWeek[] }>("/api/progress"),

  speaking: {
    get: (sid: string) => call<Session>(sp(sid)),
    create: (query: string) => call<Session>("/api/speaking/sessions", "POST", { query }),
    createTest: () => call<Session>("/api/speaking/tests", "POST"),
    submitTest: (sid: string, wav: Blob, seconds: number) =>
      call<Session>(`${sp(sid)}/test?` + new URLSearchParams({ seconds: String(seconds) }), "POST", wav),
    transcribe: (sid: string, wav: Blob) => call<{ text: string }>(`${sp(sid)}/transcribe`, "POST", wav),
    correct: (sid: string, text: string, level: string, sentences: number) =>
      call<Session>(`${sp(sid)}/correct`, "POST", { text, level, sentences }),
    updateIdeal: (sid: string, ideal: string) => call<Session>(`${sp(sid)}/ideal`, "PUT", { ideal }),
    tts: (sid: string, voiceId: string) => call<Tts>(`${sp(sid)}/tts`, "POST", { voice_id: voiceId || null }),
    addRecording: (sid: string, wav: Blob, seg: string, mode: RecMode, reference: string) =>
      call<Recording>(`${sp(sid)}/recordings?` + new URLSearchParams({ seg, mode, reference }), "POST", wav),
    evaluate: (sid: string, n: number) => call<Evaluation>(`${sp(sid)}/recordings/${n}/evaluate`, "POST"),
  },

  listening: {
    get: (sid: string) => call<ListeningSession>(`/api/listening/sessions/${sid}`),
    create: (level: string, topic: string, voiceId: string) =>
      call<ListeningSession>("/api/listening/sessions", "POST", { level, topic, voice_id: voiceId || null }),
    answer: (sid: string, i: number, answer: string, replays: number) =>
      call<ListeningSession>(`/api/listening/sessions/${sid}/items/${i}/answer`, "POST", { answer, replays }),
  },

  writing: {
    get: (sid: string) => call<WritingSession>(`/api/writing/sessions/${sid}`),
    create: (level: string, kind: WritingKind) =>
      call<WritingSession>("/api/writing/sessions", "POST", { level, kind }),
    submit: (sid: string, text: string, seconds: number) =>
      call<WritingSession>(`/api/writing/sessions/${sid}/submit`, "POST", { text, seconds }),
  },

  reading: {
    get: (sid: string) => call<ReadingSession>(`/api/reading/sessions/${sid}`),
    create: (level: string, topic: string) => call<ReadingSession>("/api/reading/sessions", "POST", { level, topic }),
    submit: (sid: string, answers: number[], readingSeconds: number) =>
      call<ReadingSession>(`/api/reading/sessions/${sid}/submit`, "POST", {
        answers,
        reading_seconds: readingSeconds,
      }),
  },

  voa: {
    zones: () => call<Record<VoaSource, VoaZone[]>>("/api/voa/zones"),
    get: (sid: string) => call<VoaSession>(`/api/voa/sessions/${sid}`),
    create: (source: VoaSource, zone: string) => call<VoaSession>("/api/voa/sessions", "POST", { source, zone }),
    listening: (sid: string, answers: number[], plays: number) =>
      call<VoaSession>(`/api/voa/sessions/${sid}/listening`, "POST", { answers, plays }),
    dictation: (sid: string, i: number, answer: string, plays: number) =>
      call<VoaSession>(`/api/voa/sessions/${sid}/dictation/${i}`, "POST", { answer, plays }),
    reading: (sid: string, answers: number[], readingSeconds: number) =>
      call<VoaSession>(`/api/voa/sessions/${sid}/reading`, "POST", { answers, reading_seconds: readingSeconds }),
  },
};
