import { useEffect, useState } from "react";
import { api, fileUrl } from "../api";
import type { Settings } from "../hooks/useSettings";
import type { Config, SessionSummary, Skill, Voice } from "../types";
import { Dialog, Kbd } from "./common";

export function SettingsDialog(props: {
  open: boolean;
  onClose: () => void;
  settings: Settings;
  onSave: (s: Settings) => void;
  voices: Voice[] | null;
  cfg: Config | null;
}) {
  const [form, setForm] = useState(props.settings);
  // 開くたびに今の設定から始める（キャンセルした編集を持ち越さない）
  useEffect(() => {
    if (props.open) setForm(props.settings);
  }, [props.open]);
  const set = (p: Partial<Settings>) => setForm((f) => ({ ...f, ...p }));
  const bool = (v: boolean) => (v ? "1" : "0");

  return (
    <Dialog open={props.open} onClose={props.onClose} title="設定">
      <div className="form">
        <label>声（ElevenLabs）</label>
        <select value={form.voice} onChange={(e) => set({ voice: e.target.value })}>
          {!props.cfg?.elevenlabs ? (
            <option value="">（APIキー未設定）</option>
          ) : props.voices == null ? (
            <option value="">（読み込み中）</option>
          ) : (
            props.voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
                {v.desc ? " — " + v.desc : ""}
              </option>
            ))
          )}
        </select>
        <label>練習のレベル</label>
        <select value={form.level} onChange={(e) => set({ level: e.target.value as Settings["level"] })}>
          <option value="B1">B1 やさしめ</option>
          <option value="B2">B2 自然</option>
          <option value="C1">C1 上級</option>
        </select>
        <label>理想文の長さ</label>
        <select value={form.sentences} onChange={(e) => set({ sentences: +e.target.value })}>
          {[3, 4, 5, 6, 8].map((n) => (
            <option key={n} value={n}>
              {n}文
            </option>
          ))}
        </select>
        <label>添削後すぐ音声生成</label>
        <select value={bool(form.autoTts)} onChange={(e) => set({ autoTts: e.target.value === "1" })}>
          <option value="1">する</option>
          <option value="0">しない</option>
        </select>
        <label>録音後に自動でAI評価</label>
        <select value={bool(form.autoEval)} onChange={(e) => set({ autoEval: e.target.value === "1" })}>
          <option value="0">しない</option>
          <option value="1">する</option>
        </select>
        <label>ループの間隔</label>
        <select value={form.loopGap} onChange={(e) => set({ loopGap: +e.target.value })}>
          {[0.5, 1, 1.5, 2.5].map((n) => (
            <option key={n} value={n}>
              {n}秒
            </option>
          ))}
        </select>
        <label>マイクのエコー除去</label>
        <select value={bool(form.echo)} onChange={(e) => set({ echo: e.target.value === "1" })}>
          <option value="1">オン</option>
          <option value="0">オフ（ヘッドホン時に音質優先）</option>
        </select>
      </div>
      {props.cfg && (
        <p className="hint">
          Gemini: {props.cfg.gemini_model} / ElevenLabs: {props.cfg.eleven_model}
        </p>
      )}
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
        <button className="btn primary" onClick={() => props.onSave(form)}>
          保存
        </button>
      </div>
    </Dialog>
  );
}

const KEYS: [string, [string, string][]][] = [
  ["共通", [
    ["1〜6", "タブ切り替え（スピーキング / リスニング / ライティング / リーディング / 教材 / 進捗）"],
    ["N", "新しい問題（写真・セット・お題・文章）"],
    ["?", "このヘルプ"],
  ]],
  ["スピーキング", [
    ["M", "説明を話す（録音開始 / 停止→文字起こし）"],
    ["⌘ Enter", "添削する"],
    ["Space", "手本を再生 / 一時停止"],
    ["↑ ↓", "前 / 次の文"],
    ["A", "全文モード切替"],
    ["L", "ループ切替"],
    ["[ ]", "速度 −/＋"],
    ["R", "シャドーイング録音（手本と同時。もう一度押すと停止）"],
    ["⇧ R", "リピート録音（手本の後に一人で話す）"],
    ["P", "最新の自分の録音を再生"],
    ["C", "聴き比べ（手本 → 自分）"],
    ["E", "選択中の録音をAIで評価"],
    ["D", "説明・添削パネルを開く"],
    ["Esc", "停止"],
  ]],
  ["リスニング", [
    ["Tab", "もう一度聞く（入力中でも使える）"],
    ["Enter", "答え合わせ"],
  ]],
  ["ライティング", [["⌘ Enter", "提出する"]]],
  ["リーディング", [["Space", "読み始める / 読み終えた"]]],
  ["教材", [
    ["Space", "全体を再生 / 一時停止（読む段階では 読み始める / 読み終えた）"],
    ["← →", "5 秒戻る / 進む"],
    ["[ ]", "速度 −/＋（1.0 / 1.25 / 1.5 倍）"],
    ["Tab", "書き取る文を再生（入力中でも使える）"],
    ["Enter", "書き取りの答え合わせ"],
  ]],
];

export function KeysDialog(props: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={props.open} onClose={props.onClose} title="キーボードショートカット">
      {KEYS.map(([section, keys]) => (
        <div key={section}>
          <div className="lbl">{section}</div>
          <div className="keys">
            {keys.map(([k, d]) => (
              <span key={k} style={{ display: "contents" }}>
                <Kbd>{k}</Kbd>
                <span>{d}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </Dialog>
  );
}

export function HistoryDialog(props: { skill: Skill; open: boolean; onClose: () => void; onPick: (id: string) => void }) {
  const [list, setList] = useState<SessionSummary[] | null>(null);
  useEffect(() => {
    if (props.open) api.sessions(props.skill).then(setList, () => setList([]));
  }, [props.open]);
  // 写真があるのはスピーキングだけ。他の技能はタイトルで一覧にする
  const photo = props.skill === "speaking";
  return (
    <Dialog open={props.open} onClose={props.onClose} title="履歴">
      <div className={photo ? "hist" : "hist text"}>
        {list == null ? (
          <p className="muted">読み込み中…</p>
        ) : list.length ? (
          list.map((s) => (
            <a
              key={s.id}
              href="#"
              onClick={(e) => {
                e.preventDefault();
                props.onPick(s.id);
              }}
            >
              {photo && (
                <img
                  src={fileUrl("speaking", s.id, "photo.jpg")}
                  loading="lazy"
                  alt=""
                  onError={(e) => (e.currentTarget.style.visibility = "hidden")}
                />
              )}
              <div>
                {s.created}
                {s.score != null && ` · ${s.score} 点`}
                <br />
                {s.title}
              </div>
            </a>
          ))
        ) : (
          <p className="muted">まだありません</p>
        )}
      </div>
    </Dialog>
  );
}
