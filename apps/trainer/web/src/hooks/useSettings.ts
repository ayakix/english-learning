import { useCallback, useState } from "react";

export type Settings = {
  voice: string;
  level: "B1" | "B2" | "C1";
  sentences: number;
  autoTts: boolean;
  autoEval: boolean;
  loopGap: number;
  echo: boolean;
  speed: number;
};

const DEFAULTS: Settings = {
  voice: "",
  level: "B2",
  sentences: 5,
  autoTts: true,
  autoEval: false,
  loopGap: 1,
  echo: true,
  speed: 1,
};

// MVP（ps_settings）とは値の型が違うため、別のキーで保存する
const KEY = "trainer:settings";

function load(): Settings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return DEFAULTS;
  }
}

export function useSettings() {
  const [settings, setState] = useState<Settings>(load);
  const update = useCallback((patch: Partial<Settings>) => {
    setState((s) => {
      const next = { ...s, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // プライベートウィンドウなどで保存できなくても、その場の設定としては使える
      }
      return next;
    });
  }, []);
  return [settings, update] as const;
}
