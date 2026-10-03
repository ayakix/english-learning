import type { Skill } from "../types";

// リロードしても直前の練習から続けられるよう、技能ごとに最後に開いたセッションを覚えておく
const key = (skill: Skill) => `trainer:last:${skill}`;

export function rememberLast(skill: Skill, id: string) {
  try {
    localStorage.setItem(key(skill), id);
  } catch {
    // 保存できなくても練習は続けられる
  }
}

/** ?s=<id> があればそれを優先する（journal から特定の練習へリンクできるように） */
export function lastId(skill: Skill, isCurrentTab: boolean): string | null {
  const fromUrl = new URLSearchParams(location.search).get("s");
  if (fromUrl && isCurrentTab) return fromUrl;
  try {
    return localStorage.getItem(key(skill));
  } catch {
    return null;
  }
}
