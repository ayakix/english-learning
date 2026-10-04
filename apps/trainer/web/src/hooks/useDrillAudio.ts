import { useContext, useEffect, useRef, useState } from "react";
import { PageActive } from "./useHotkeys";
import { useToast } from "./useToast";
import { errMsg } from "../lib/util";

/**
 * ドリルの音声を 1 つずつ再生する。どれを再生中かを key で持ち、同じ key をもう一度押したら止める。
 * 別のタブに切り替えたら止める（全ページを描画したまま隠しているため）。
 */
export function useDrillAudio() {
  const toast = useToast();
  const active = useContext(PageActive);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef(new Audio());

  useEffect(() => {
    const a = audio.current;
    const end = () => setPlaying(null);
    a.addEventListener("ended", end);
    a.addEventListener("pause", end);
    return () => {
      a.pause();
      a.removeEventListener("ended", end);
      a.removeEventListener("pause", end);
    };
  }, []);

  useEffect(() => {
    if (!active) audio.current.pause();
  }, [active]);

  function play(url: string, key: string) {
    const a = audio.current;
    if (playing === key) return a.pause();
    a.src = url;
    a.play().then(
      () => setPlaying(key),
      (e) => toast("再生できません: " + errMsg(e), true),
    );
  }

  return { playing, play, stop: () => audio.current.pause() };
}
