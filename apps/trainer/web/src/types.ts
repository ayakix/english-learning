// サーバーの session.json と同じ形（src/trainer/ の各技能のモジュール）

export type Skill = "speaking" | "listening" | "writing" | "reading" | "voa";

export type Result = { score: number | null; details: Record<string, number | string | null> };

// どの技能の session.json も持つ共通の項目
export type Base = { id: string; skill: Skill; created: string; title: string; result: Result };

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

export type TestGrade = {
  toeic: number;
  score: number;
  content: number;
  grammar: number;
  vocabulary: number;
  delivery: number;
  feedback_ja: string;
};

// テスト形式（TOEIC の写真描写）のときだけ。model_answer は採点前は空で返る
export type SpeakingTest = {
  stock_id: string;
  prep: number;
  response: number;
  model_answer: string;
  answer: string | null;
  seconds: number | null;
  grade: TestGrade | null;
};

export type Session = Base & {
  query: string;
  photo: Photo;
  attempts: Attempt[];
  correction: Correction | null;
  tts: Tts | null;
  recordings: Recording[];
  test?: SpeakingTest;
};

export type SessionSummary = { id: string; created: string; title: string; score: number | null };

export type Fix = { before: string; after: string; reason_ja: string };
export type Expression = { en: string; ja: string };

// ---------------------------------------------------------------- listening
export type DiffToken = { t: string; status: "ok" | "wrong" | "missing" | "extra"; heard?: string };

// 答える前は i と file だけが返る
export type ListeningItem = {
  i: number;
  file: string;
  text?: string;
  ja?: string;
  points_ja?: string;
  answer?: string | null;
  replays?: number;
  accuracy?: number;
  diff?: DiffToken[];
};

export type ListeningSession = Base & { level: string; topic: string; items: ListeningItem[] };

// ---------------------------------------------------------------- writing
export type WritingGrade = {
  task: number;
  grammar: number;
  vocabulary: number;
  coherence: number;
  overall: number;
  cefr: string;
  corrections: Fix[];
  improved: string;
  key_expressions: Expression[];
  feedback_ja: string;
};

export type WritingSubmission = {
  time: string;
  text: string;
  words: number;
  seconds: number;
  wpm: number | null;
  grade: WritingGrade;
};

export type WritingKind = "email" | "opinion" | "story";

export type WritingSession = Base & {
  level: string;
  kind: WritingKind;
  task: { title: string; task: string; task_ja: string; min_words: number; max_words: number };
  submissions: WritingSubmission[];
};

// ---------------------------------------------------------------- reading
// 提出前は q と options だけが返る
export type Question = { q: string; options: string[]; answer?: number; explanation_ja?: string };

export type ReadingSession = Base & {
  level: string;
  topic: string;
  passage: string;
  words: number;
  questions: Question[];
  glossary: Expression[];
  submission: { time: string; answers: number[]; correct: number; reading_seconds: number; wpm: number | null } | null;
};

// ---------------------------------------------------------------- voa
export type VoaStage = "listening" | "dictation" | "reading" | "done";

// 書き取る前は i / start / end / answer / plays だけが返る
export type VoaDictation = {
  i: number;
  start: number;
  end: number;
  answer: string | null;
  plays: number;
  text?: string;
  ja?: string;
  points_ja?: string;
  accuracy?: number;
  diff?: DiffToken[];
};

export type VoaQuiz = { questions: Question[]; answers: number[] | null; correct: number | null };

export type VoaSession = Base & {
  stage: VoaStage;
  source: {
    site: string;
    url: string | null;
    title: string;
    published: string;
    credit: string;
    license: string;
    audio_url: string | null;
    zone: string;
    // AI 教材のときだけ
    stock_id?: string;
    level?: string;
    format?: "monologue" | "dialogue";
  };
  // 本文・語彙は「読む」の段階になるまで空で返る
  paragraphs: { text: string; heading: boolean }[];
  glossary: { word: string; definition: string }[];
  words: number;
  duration: number;
  audio_wpm: number | null;
  summary_ja: string;
  listening: VoaQuiz & { plays: number };
  dictation: VoaDictation[];
  reading: VoaQuiz & { reading_seconds: number | null; wpm: number | null };
};

export type VoaSource = "voa" | "ai";
// left：AI 教材でまだ使っていない本数
export type VoaZone = { key: string; name: string; left?: number };

// ---------------------------------------------------------------- progress
export type ProgressPoint = { date: string; skill: Skill; id: string; score: number; details: Result["details"] };
export type ProgressWeek = { week: string; skill: Skill; count: number; avg: number; wpm?: number };

export type Config = {
  gemini: boolean;
  elevenlabs: boolean;
  unsplash: boolean;
  gemini_model: string;
  eleven_model: string;
  default_voice: string;
};

export type Voice = { id: string; name: string; desc: string; category: string };
