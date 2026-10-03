import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type ToastFn = (msg: string, err?: boolean) => void;

const Ctx = createContext<ToastFn>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ msg: string; err: boolean; on: boolean }>({ msg: "", err: false, on: false });
  const timer = useRef<number>(undefined);
  const toast = useCallback<ToastFn>((msg, err = false) => {
    setT({ msg, err, on: true });
    clearTimeout(timer.current);
    // エラーは原因を読めるように長めに出す
    timer.current = window.setTimeout(() => setT((x) => ({ ...x, on: false })), err ? 7000 : 2600);
  }, []);
  return (
    <Ctx.Provider value={toast}>
      {children}
      <div className={`toast${t.on ? " on" : ""}${t.err ? " err" : ""}`}>{t.msg}</div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
