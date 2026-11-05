// 書きかけをタブの中（sessionStorage）に残す（ADR-0071）。
//
// SSO で入ったログインが続けられないと、画面はログイン画面に替わり、IdP と全画面で往復してから
// 元の画面へ戻る。React の状態は消えるので、**書きかけは書くたびにここへ写しておく。**
// 戻ってきたときに同じ鍵で読み直せば、書きかけがそのまま出る。
//
// - 値が `null` になったら（保存した・空にした）消す
// - サインアウトしたら全部消す（{@link clearSessionDrafts}。同じタブで別の人が入ることがある）
// - 読めない・書けないブラウザでは、ふつうの状態としてだけ振る舞う
import { useCallback, useState } from 'react';

const PREFIX = 'wbs.draft:';

const read = <T>(key: string, initial: T | null): T | null => {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key);
    return raw === null ? initial : (JSON.parse(raw) as T);
  } catch {
    return initial;
  }
};

const write = (key: string, value: unknown): void => {
  try {
    if (value === null) window.sessionStorage.removeItem(PREFIX + key);
    else window.sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // 残せなくても書きかけは画面に残っている
  }
};

export const useSessionDraft = <T>(key: string, initial: T | null = null) => {
  const [value, setValue] = useState<T | null>(() => read<T>(key, initial));
  const update = useCallback(
    (next: T | null | ((current: T | null) => T | null)) => {
      setValue((current) => {
        const resolved = typeof next === 'function' ? (next as (current: T | null) => T | null)(current) : next;
        write(key, resolved);
        return resolved;
      });
    },
    [key],
  );
  return [value, update] as const;
};

/** 書きかけを全部消す（サインアウトしたとき）。 */
export const clearSessionDrafts = (): void => {
  try {
    for (const key of Object.keys(window.sessionStorage)) {
      if (key.startsWith(PREFIX)) window.sessionStorage.removeItem(key);
    }
  } catch {
    // 消せなくても、次に保存すれば上書きされる
  }
};
