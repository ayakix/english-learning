import { useEffect } from "react";
import { api } from "../api";

const INTERVAL_MS = 60_000;
// 開きっぱなしで放置したタブを練習時間に数えないよう、直近に操作があったときだけ通知する
const IDLE_MS = 2 * 60_000;
const EVENTS = ["keydown", "pointerdown", "scroll", "input"] as const;

/**
 * 画面が使われている間、1 分ごとにサーバーへ通知する（外から練習した時間を journal に残すため）。
 * 手元か外かは画面では判定せず常に送り、サーバーが Cloudflare Access のヘッダーで判定する。
 */
export function useActivity() {
  useEffect(() => {
    let last = Date.now();
    const touch = () => (last = Date.now());
    // scroll はバブリングしないので capture で拾う（ページ内のスクロール領域も含めるため）
    EVENTS.forEach((e) => window.addEventListener(e, touch, { capture: true, passive: true }));
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible" || Date.now() - last > IDLE_MS) return;
      // 記録できなくても練習の邪魔はしたくないので、失敗は無視する
      api.activity().catch(() => {});
    }, INTERVAL_MS);
    return () => {
      clearInterval(timer);
      EVENTS.forEach((e) => window.removeEventListener(e, touch, { capture: true }));
    };
  }, []);
}
