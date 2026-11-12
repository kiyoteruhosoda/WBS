// Keep drafts within the tab (sessionStorage) (ADR-0071).
//
// When an SSO session can't be continued, the UI switches to the sign-in page and does a full-page round trip with the IdP before
// returning to the original page. React state is lost, so **drafts are copied here on every edit.**
// Reading with the same key on return brings the draft back as is.
//
// - Removed when the value becomes `null` (saved or cleared)
// - All removed on sign-out ({@link clearSessionDrafts}; someone else may sign in on the same tab)
// - In browsers where storage can't be read or written, it behaves as plain state
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
    // Even if it can't be stored, the draft is still on screen
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

/** Remove all drafts (on sign-out). */
export const clearSessionDrafts = (): void => {
  try {
    for (const key of Object.keys(window.sessionStorage)) {
      if (key.startsWith(PREFIX)) window.sessionStorage.removeItem(key);
    }
  } catch {
    // Even if it can't be removed, the next save overwrites it
  }
};
