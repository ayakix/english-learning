import { createContext, useContext } from "react";
import type { Config, Voice } from "../types";
import type { Settings } from "./useSettings";

// どのページからも使う設定とサーバー情報（props で何段も渡さないため）
export type AppCtx = {
  cfg: Config | null;
  voices: Voice[] | null;
  settings: Settings;
  updateSettings: (p: Partial<Settings>) => void;
};

export const AppContext = createContext<AppCtx>(null!);

export const useApp = () => useContext(AppContext);
