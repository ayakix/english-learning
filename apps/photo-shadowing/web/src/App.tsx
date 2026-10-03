import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { CorrectionPanel } from "./components/CorrectionPanel";
import { DescribePanel } from "./components/DescribePanel";
import { HistoryDialog, KeysDialog, SettingsDialog } from "./components/Dialogs";
import { PhotoPanel } from "./components/PhotoPanel";
import { ShadowPanel, type ShadowHandle } from "./components/ShadowPanel";
import { Kbd, Spinner } from "./components/common";
import { useHotkeys } from "./hooks/useHotkeys";
import { useSettings } from "./hooks/useSettings";
import { useToast } from "./hooks/useToast";
import { errMsg } from "./lib/util";
import type { Config, Session, Voice } from "./types";

// リロードしても直前の写真から続けられるようにする
const LAST_KEY = "photo-shadowing:last";

function remember(id: string) {
  try {
    localStorage.setItem(LAST_KEY, id);
  } catch {
    // 保存できなくても練習は続けられる
  }
}

export default function App() {
  const toast = useToast();
  const [settings, updateSettings] = useSettings();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [query, setQuery] = useState("");
  const [desc, setDesc] = useState("");
  const [collapsed, setCollapsed] = useState({ desc: false, corr: false });
  const [loadingPhoto, setLoadingPhoto] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [dialog, setDialog] = useState<"settings" | "keys" | "history" | null>(null);
  const shadow = useRef<ShadowHandle>(null);
  const shadowWrap = useRef<HTMLDivElement>(null);

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
      // ?s=<id> があればそのセッションを開く（journal から特定の練習へリンクできるように）
      const last = new URLSearchParams(location.search).get("s") ?? localStorage.getItem(LAST_KEY);
      if (last) await openSession(last).catch(() => {});
    })();
  }, []);

  const expandAll = () => setCollapsed({ desc: false, corr: false });

  function focusShadow() {
    setCollapsed({ desc: true, corr: true });
    setTimeout(() => shadowWrap.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  async function openSession(id: string) {
    shadow.current?.stopAll();
    const s = await api.session(id);
    setSession(s);
    remember(s.id);
    setDesc(s.attempts.at(-1)?.text ?? "");
    if (s.tts) focusShadow();
    else expandAll();
  }

  async function newPhoto() {
    if (loadingPhoto) return;
    shadow.current?.stopAll();
    setLoadingPhoto(true);
    try {
      const s = await api.newSession(query);
      setSession(s);
      remember(s.id);
      setDesc("");
      expandAll();
    } catch (e) {
      toast("写真の取得に失敗: " + errMsg(e), true);
    } finally {
      setLoadingPhoto(false);
    }
  }

  async function makeTts(s = session) {
    if (!s?.correction || ttsLoading) return;
    setTtsLoading(true);
    try {
      const tts = await api.tts(s.id, settings.voice);
      setSession((cur) => (cur && cur.id === s.id ? { ...cur, tts } : cur));
      focusShadow();
    } catch (e) {
      toast("音声生成失敗: " + errMsg(e), true);
    } finally {
      setTtsLoading(false);
    }
  }

  async function doCorrect() {
    if (!session || correcting) return;
    const text = desc.trim();
    if (!text) return toast("説明文がありません。M で話してください");
    setCorrecting(true);
    try {
      const s = await api.correct(session.id, text, settings.level, settings.sentences);
      setSession(s);
      setCollapsed((c) => ({ ...c, corr: false }));
      if (settings.autoTts) makeTts(s);
    } catch (e) {
      toast("添削失敗: " + errMsg(e), true);
    } finally {
      setCorrecting(false);
    }
  }

  async function saveIdeal(ideal: string) {
    if (!session) return;
    try {
      const s = await api.updateIdeal(session.id, ideal);
      setSession(s);
      makeTts(s);
    } catch (e) {
      toast("保存に失敗: " + errMsg(e), true);
    }
  }

  useHotkeys({
    n: newPhoto,
    N: newPhoto,
    "?": () => setDialog("keys"),
    d: expandAll,
    D: expandAll,
  });

  const status = (ok: boolean | undefined, name: string) => (
    <span>
      {name}: <b className={ok ? "" : "ng"}>{ok ? "✓" : "未設定"}</b>
    </span>
  );

  return (
    <>
      <header>
        <h1>📷 Photo Shadowing</h1>
        <button className="btn sm" onClick={newPhoto} disabled={loadingPhoto}>
          {loadingPhoto ? (
            <>
              <Spinner /> 取得中
            </>
          ) : (
            <>
              新しい写真 <Kbd>N</Kbd>
            </>
          )}
        </button>
        <button className="btn sm" onClick={() => setDialog("history")}>
          履歴
        </button>
        <span className="sp" />
        {cfg && (
          <div className="status">
            {status(cfg.gemini, "Gemini")}
            {status(cfg.elevenlabs, "ElevenLabs")}
            {status(cfg.unsplash, "Unsplash")}
          </div>
        )}
        <button className="btn sm" onClick={() => setDialog("keys")} title="ショートカット">
          ⌨ <Kbd>?</Kbd>
        </button>
        <button className="btn sm" onClick={() => setDialog("settings")}>
          設定
        </button>
      </header>

      <main>
        <PhotoPanel session={session} query={query} onQuery={setQuery} onNew={newPhoto} />
        <div className="col">
          <DescribePanel
            session={session}
            text={desc}
            onText={setDesc}
            echo={settings.echo}
            collapsed={collapsed.desc}
            onToggle={() => setCollapsed((c) => ({ ...c, desc: !c.desc }))}
            onExpand={() => setCollapsed((c) => ({ ...c, desc: false }))}
            onBeforeRecord={() => shadow.current?.stopAll()}
            onCorrect={doCorrect}
            correcting={correcting}
          />
          {session?.correction && (
            <CorrectionPanel
              correction={session.correction}
              collapsed={collapsed.corr}
              onToggle={() => setCollapsed((c) => ({ ...c, corr: !c.corr }))}
              onSaveIdeal={saveIdeal}
            />
          )}
          {session?.correction && (
            <div ref={shadowWrap}>
              <ShadowPanel
                ref={shadow}
                session={session}
                settings={settings}
                updateSettings={updateSettings}
                ttsLoading={ttsLoading}
                onMakeTts={() => makeTts()}
                onRecordingsChange={(fn) => setSession((s) => (s ? { ...s, recordings: fn(s.recordings) } : s))}
              />
            </div>
          )}
        </div>
      </main>

      <SettingsDialog
        open={dialog === "settings"}
        onClose={() => setDialog(null)}
        settings={settings}
        voices={voices}
        cfg={cfg}
        onSave={(next) => {
          if (next.voice !== settings.voice && session?.correction)
            toast("声を変更しました。「音声を作り直す」で作り直せます");
          updateSettings(next);
          setDialog(null);
        }}
      />
      <KeysDialog open={dialog === "keys"} onClose={() => setDialog(null)} />
      <HistoryDialog
        open={dialog === "history"}
        onClose={() => setDialog(null)}
        onPick={(id) => {
          setDialog(null);
          openSession(id).catch((e) => toast("読み込みに失敗: " + errMsg(e), true));
        }}
      />
    </>
  );
}
