import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearSessionDrafts } from './sessionDraft';

/** 試験は node で走るので、ブラウザの保存領域を素の物で代える（Object.keys で鍵が見えるように） */
const fakeStorage = () => {
  const store: Record<string, string> = {};
  return Object.defineProperties(store, {
    getItem: { value: (key: string) => store[key] ?? null, enumerable: false },
    setItem: { value: (key: string, value: string) => void (store[key] = value), enumerable: false },
    removeItem: { value: (key: string) => void delete store[key], enumerable: false },
  }) as unknown as Storage;
};

beforeEach(() => {
  vi.stubGlobal('window', { sessionStorage: fakeStorage() });
});

describe('書きかけ（ADR-0071）', () => {
  it('サインアウトでこのアプリの書きかけだけを消す', () => {
    window.sessionStorage.setItem('wbs.draft:inbox', '{"title":"a","memo":""}');
    window.sessionStorage.setItem('wbs.sso.silentAttempted', '1');
    clearSessionDrafts();
    expect(window.sessionStorage.getItem('wbs.draft:inbox')).toBeNull();
    expect(window.sessionStorage.getItem('wbs.sso.silentAttempted')).toBe('1');
  });
});
