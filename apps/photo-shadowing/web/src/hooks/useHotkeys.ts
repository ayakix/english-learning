import { useEffect, useRef } from "react";

type Handlers = Record<string, () => void>;

/**
 * 1 文字キーのショートカットを登録する（キーは e.key の値。"R" は Shift+R）
 * 入力欄にフォーカスがあるとき・ダイアログが開いているとき・修飾キー付きのときは反応しない。
 * ハンドラは毎回の描画で変わるので ref に入れ、リスナーの付け直しを避ける。
 */
export function useHotkeys(handlers: Handlers) {
  const ref = useRef(handlers);
  ref.current = handlers;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /^(TEXTAREA|INPUT|SELECT)$/.test(document.activeElement?.tagName ?? "");
      if (typing || e.metaKey || e.ctrlKey || e.altKey || document.querySelector("dialog[open]")) return;
      const fn = ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}
