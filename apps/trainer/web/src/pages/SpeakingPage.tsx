import { useContext, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { CorrectionPanel } from "../components/CorrectionPanel";
import { DescribePanel } from "../components/DescribePanel";
import { HistoryDialog } from "../components/Dialogs";
import { PhotoPanel } from "../components/PhotoPanel";
import { ShadowPanel, type ShadowHandle } from "../components/ShadowPanel";
import { PageBar } from "../components/common";
import { useApp } from "../hooks/useApp";
import { PageActive, useHotkeys } from "../hooks/useHotkeys";
import { useToast } from "../hooks/useToast";
import { lastId, rememberLast } from "../lib/last";
import { errMsg } from "../lib/util";
import type { Session } from "../types";

/** スピーキング：写真を英語で描写 → 添削 → 理想文のシャドーイング */
export function SpeakingPage() {
  const toast = useToast();
  const active = useContext(PageActive);
  const { settings, updateSettings } = useApp();
  const [session, setSession] = useState<Session | null>(null);
  const [query, setQuery] = useState("");
  const [desc, setDesc] = useState("");
  const [collapsed, setCollapsed] = useState({ desc: false, corr: false });
  const [loadingPhoto, setLoadingPhoto] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [history, setHistory] = useState(false);
  const shadow = useRef<ShadowHandle>(null);
  const shadowWrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = lastId("speaking", active);
    if (id) openSession(id).catch(() => {});
  }, []);

  // 別のタブに移ったら、手本の再生や録音を止める
  useEffect(() => {
    if (!active) shadow.current?.stopAll();
  }, [active]);

  const expandAll = () => setCollapsed({ desc: false, corr: false });

  function focusShadow() {
    setCollapsed({ desc: true, corr: true });
    setTimeout(() => shadowWrap.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  async function openSession(id: string) {
    shadow.current?.stopAll();
    const s = await api.speaking.get(id);
    setSession(s);
    rememberLast("speaking", s.id);
    setDesc(s.attempts.at(-1)?.text ?? "");
    if (s.tts) focusShadow();
    else expandAll();
  }

  async function newPhoto() {
    if (loadingPhoto) return;
    shadow.current?.stopAll();
    setLoadingPhoto(true);
    try {
      const s = await api.speaking.create(query);
      setSession(s);
      rememberLast("speaking", s.id);
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
      const tts = await api.speaking.tts(s.id, settings.voice);
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
      const s = await api.speaking.correct(session.id, text, settings.level, settings.sentences);
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
      const s = await api.speaking.updateIdeal(session.id, ideal);
      setSession(s);
      makeTts(s);
    } catch (e) {
      toast("保存に失敗: " + errMsg(e), true);
    }
  }

  useHotkeys({ n: newPhoto, N: newPhoto, d: expandAll, D: expandAll });

  return (
    <>
      <PageBar
        newLabel="新しい写真"
        busy={loadingPhoto}
        busyLabel="取得中"
        onNew={newPhoto}
        onHistory={() => setHistory(true)}
      />
      <main className="split">
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
      <HistoryDialog
        skill="speaking"
        open={history}
        onClose={() => setHistory(false)}
        onPick={(id) => {
          setHistory(false);
          openSession(id).catch((e) => toast("読み込みに失敗: " + errMsg(e), true));
        }}
      />
    </>
  );
}
