import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  forgetSilentMarks,
  markSilentAttempt,
  rememberSignedOut,
  returnPathOf,
  shouldTrySilently,
} from './silentSignIn';

const at = (url: string) => {
  const parsed = new URL(url, 'https://wbs.example.com');
  return { pathname: parsed.pathname, search: parsed.search };
};

/** 試験は node で走るので、ブラウザの保存領域を Map で代える */
const fakeStorage = (): Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> => {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => void values.set(key, value),
    removeItem: (key) => void values.delete(key),
  };
};

beforeEach(() => {
  vi.stubGlobal('sessionStorage', fakeStorage());
  vi.stubGlobal('localStorage', fakeStorage());
});

describe('IdP で入っているかを黙って確かめるか（ADR-0062）', () => {

  it('初めて開いたログイン画面・保護された画面では試す', () => {
    expect(shouldTrySilently(at('/login'))).toBe(true);
    expect(shouldTrySilently(at('/login?next=%2Fgantt'))).toBe(true);
    expect(shouldTrySilently(at('/tasks?project=3'))).toBe(true);
  });

  it('同じタブでは 1 回だけ', () => {
    expect(markSilentAttempt()).toBe(true);
    expect(shouldTrySilently(at('/login'))).toBe(false);
  });

  it('サインアウトした後は、次に入るまで試さない', () => {
    rememberSignedOut();
    expect(shouldTrySilently(at('/login'))).toBe(false);
    forgetSilentMarks();
    expect(shouldTrySilently(at('/login'))).toBe(true);
  });

  it('保存領域が使えなければ試さない（1 回だけの印が置けずループになる）', () => {
    vi.stubGlobal('sessionStorage', undefined);
    expect(shouldTrySilently(at('/login'))).toBe(false);
    expect(markSilentAttempt()).toBe(false);
  });

  it('ログイン画面にエラーや断られた印が付いていたら試さない', () => {
    expect(shouldTrySilently(at('/login?error=access_denied'))).toBe(false);
    expect(shouldTrySilently(at('/login?sso_silent=1&next=%2Fgantt'))).toBe(false);
  });

  it('断られた後でも、本人が再読み込みしたらもう 1 回試す（ADR-0063）', () => {
    expect(markSilentAttempt()).toBe(true);
    expect(shouldTrySilently(at('/login?sso_silent=1&next=%2Fgantt'), true)).toBe(true);
    expect(shouldTrySilently(at('/login?sso_silent=1'), true)).toBe(true);
  });

  it('再読み込みでも、エラーが付いている・サインアウトした後は試さない', () => {
    expect(shouldTrySilently(at('/login?error=access_denied'), true)).toBe(false);
    rememberSignedOut();
    expect(shouldTrySilently(at('/login?sso_silent=1'), true)).toBe(false);
  });
});

describe('ログイン後に戻る先', () => {
  it('ログイン画面なら next、それ以外は今の画面', () => {
    expect(returnPathOf(at('/login?sso_silent=1&next=%2Fgantt%3Fp%3D1'))).toBe('/gantt?p=1');
    expect(returnPathOf(at('/login'))).toBe('/');
    expect(returnPathOf(at('/login?next=%2F%2Fevil.example'))).toBe('/');
    expect(returnPathOf(at('/tasks?project=3'))).toBe('/tasks?project=3');
  });
});
