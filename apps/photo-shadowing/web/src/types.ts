// サーバーの session.json と同じ形（src/photo_shadowing/server.py）

export type Credit = { name: string; profile: string; link: string; alt: string };

export type Photo = { source: "unsplash" | "picsum"; url: string | null; credit: Credit };

export type Attempt = { time: string; text: string; score: number | null };

export type Correction = {
  corrected: string;
  corrections: { before: string; after: string; reason_ja: string }[];
  ideal: string;
  key_expressions: { en: string; ja: string }[];
  feedback_ja: string;
  score: number;
  original: string;
  level: string;
};

export type Sentence = { text: string; start: number; end: number };
// t: 単語, s/e: 開始・終了秒, i: 文の番号
export type Word = { t: string; s: number; e: number; i: number };

export type Tts = { file: string; text: string; sentences: Sentence[]; words: Word[] };

export type Evaluation = {
  heard: string;
  overall: number;
  pronunciation: number;
  fluency: number;
  intonation: number;
  completeness: number;
  word_issues: { word: string; problem_ja: string; tip_ja: string }[];
  good_points_ja: string[];
  improvements_ja: string[];
  summary_ja: string;
};

export type RecMode = "overlap" | "repeat";

// seg: "all"（全文）または文の番号の文字列
export type Recording = {
  n: number;
  file: string;
  seg: string;
  mode: RecMode;
  reference: string;
  time: string;
  evaluation: Evaluation | null;
};

export type Session = {
  id: string;
  created: string;
  query: string;
  photo: Photo;
  attempts: Attempt[];
  correction: Correction | null;
  tts: Tts | null;
  recordings: Recording[];
};

export type SessionSummary = { id: string; created: string; has_ideal: boolean; recordings: number; best: number | null };

export type Config = {
  gemini: boolean;
  elevenlabs: boolean;
  unsplash: boolean;
  gemini_model: string;
  eleven_model: string;
  default_voice: string;
};

export type Voice = { id: string; name: string; desc: string; category: string };
