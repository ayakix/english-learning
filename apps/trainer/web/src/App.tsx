import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { KeysDialog, SettingsDialog } from "./components/Dialogs";
import { Kbd } from "./components/common";
import { useActivity } from "./hooks/useActivity";
import { AppContext } from "./hooks/useApp";
import { PageActive, useHotkeys } from "./hooks/useHotkeys";
import { useSettings } from "./hooks/useSettings";
import { useToast } from "./hooks/useToast";
import { LessonPage } from "./pages/LessonPage";
import { ListeningPage } from "./pages/ListeningPage";
import { ProgressPage } from "./pages/ProgressPage";
import { PronunciationPage } from "./pages/PronunciationPage";
import { ReadingPage } from "./pages/ReadingPage";
import { SpeakingPage } from "./pages/SpeakingPage";
import { VersantPage } from "./pages/VersantPage";
import { WritingPage } from "./pages/WritingPage";
import type { Config, Voice } from "./types";

const TABS: { key: string; label: string; page: ReactNode }[] = [
  { key: "speaking", label: "スピーキング", page: <SpeakingPage /> },
  { key: "listening", label: "リスニング", page: <ListeningPage /> },
  { key: "writing", label: "ライティング", page: <WritingPage /> },
  { key: "reading", label: "リーディング", page: <ReadingPage /> },
  // 既存タブのキー（1〜4）を変えないよう、後ろに足す
  { key: "lesson", label: "教材", page: <LessonPage /> },
  { key: "pronunciation", label: "発音", page: <PronunciationPage /> },
  { key: "versant", label: "Versant", page: <VersantPage /> },
  { key: "progress", label: "進捗", page: <ProgressPage /> },
];

// タブは URL のハッシュ（#listening など）で持ち、リロードやリンクで同じタブを開けるようにする
const tabFromHash = () => {
  const h = location.hash.slice(1);
  return TABS.some((t) => t.key === h) ? h : "speaking";
};

export default function App() {
  const toast = useToast();
  const [settings, updateSettings] = useSettings();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [tab, setTab] = useState(tabFromHash);
  const [dialog, setDialog] = useState<"settings" | "keys" | null>(null);
  useActivity();

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // スマホ幅ではタブが横スクロールになるので、選んだタブが隠れないように見える位置まで動かす
  useEffect(() => {
    document.querySelector(".tabs a.on")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [tab]);

  useEffect(() => {
    (async () => {
      let c: Config;
      try {
        c = await api.config();
      } catch {
        return toast("サーバーに接続できません", true);
      }
      setCfg(c);
      if (!settings.voice && c.default_voice) updateSettings({ voice: c.default_voice });
      if (c.elevenlabs)
        api.voices().then(
          (vs) => {
            setVoices(vs);
            if (!settings.voice && !c.default_voice && vs.length) updateSettings({ voice: vs[0].id });
          },
          () => setVoices([]),
        );
    })();
  }, []);

  const go = (key: string) => (location.hash = key);

  useHotkeys({
    "?": () => setDialog("keys"),
    ...Object.fromEntries(TABS.map((t, i) => [String(i + 1), () => go(t.key)])),
  });

  const status = (ok: boolean | undefined, name: string) => (
    <span>
      {name}: <b className={ok ? "" : "ng"}>{ok ? "✓" : "未設定"}</b>
    </span>
  );

  return (
    <AppContext.Provider value={{ cfg, voices, settings, updateSettings }}>
      <header>
        <h1>English Trainer</h1>
        <nav className="tabs">
          {TABS.map((t, i) => (
            <a key={t.key} href={`#${t.key}`} className={t.key === tab ? "on" : ""} title={`${i + 1} キー`}>
              {t.label}
            </a>
          ))}
        </nav>
        <span className="sp" />
        {cfg && (
          <div className="status">
            {status(cfg.gemini, "Gemini")}
            {status(cfg.elevenlabs, "ElevenLabs")}
            {status(cfg.unsplash, "Unsplash")}
          </div>
        )}
        <span className="hint">{settings.level}</span>
        <button className="btn sm" onClick={() => setDialog("keys")} title="ショートカット">
          ⌨ <Kbd>?</Kbd>
        </button>
        <button className="btn sm" onClick={() => setDialog("settings")}>
          設定
        </button>
      </header>

      {TABS.map((t) => (
        <PageActive.Provider key={t.key} value={t.key === tab}>
          <div className={t.key === tab ? "" : "page-hidden"}>{t.page}</div>
        </PageActive.Provider>
      ))}

      <SettingsDialog
        open={dialog === "settings"}
        onClose={() => setDialog(null)}
        settings={settings}
        voices={voices}
        cfg={cfg}
        onSave={(next) => {
          if (next.voice !== settings.voice && tab === "speaking")
            toast("声を変更しました。「音声を作り直す」で作り直せます");
          updateSettings(next);
          setDialog(null);
        }}
      />
      <KeysDialog open={dialog === "keys"} onClose={() => setDialog(null)} />
    </AppContext.Provider>
  );
}
