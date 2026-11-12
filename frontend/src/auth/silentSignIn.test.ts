import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  forgetSilentMarks,
  markSilentAttempt,
  rememberSignedOut,
  returnPathOf,
  signedOutHere,
  shouldTrySilently,
} from './silentSignIn';

const at = (url: string) => {
  const parsed = new URL(url, 'https://wbs.example.com');
  return { pathname: parsed.pathname, search: parsed.search };
};

/** Tests run in node, so browser storage is replaced with a Map */
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

describe('whether to silently check the IdP sign-in (ADR-0062)', () => {

  it('tries on a freshly opened sign-in page or protected page', () => {
    expect(shouldTrySilently(at('/login'))).toBe(true);
    expect(shouldTrySilently(at('/login?next=%2Fgantt'))).toBe(true);
    expect(shouldTrySilently(at('/tasks?project=3'))).toBe(true);
  });

  it('only once per tab', () => {
    expect(markSilentAttempt()).toBe(true);
    expect(shouldTrySilently(at('/login'))).toBe(false);
  });

  it('does not try after sign-out until the next sign-in', () => {
    rememberSignedOut();
    expect(shouldTrySilently(at('/login'))).toBe(false);
    forgetSilentMarks();
    expect(shouldTrySilently(at('/login'))).toBe(true);
  });

  it('does not try without storage (the one-shot marker cannot be stored, which would loop)', () => {
    vi.stubGlobal('sessionStorage', undefined);
    expect(shouldTrySilently(at('/login'))).toBe(false);
    expect(markSilentAttempt()).toBe(false);
  });

  it('does not try when the sign-in page carries an error or refusal marker', () => {
    expect(shouldTrySilently(at('/login?error=access_denied'))).toBe(false);
    expect(shouldTrySilently(at('/login?sso_silent=1&next=%2Fgantt'))).toBe(false);
  });

  it('tries once more after a refusal when the user reloads (ADR-0063)', () => {
    expect(markSilentAttempt()).toBe(true);
    expect(shouldTrySilently(at('/login?sso_silent=1&next=%2Fgantt'), true)).toBe(true);
    expect(shouldTrySilently(at('/login?sso_silent=1'), true)).toBe(true);
  });

  it('does not try on reload with an error or after sign-out', () => {
    expect(shouldTrySilently(at('/login?error=access_denied'), true)).toBe(false);
    rememberSignedOut();
    expect(shouldTrySilently(at('/login?sso_silent=1'), true)).toBe(false);
  });
});

describe('return target after sign-in', () => {
  it('next on the sign-in page, otherwise the current page', () => {
    expect(returnPathOf(at('/login?sso_silent=1&next=%2Fgantt%3Fp%3D1'))).toBe('/gantt?p=1');
    expect(returnPathOf(at('/login'))).toBe('/');
    expect(returnPathOf(at('/login?next=%2F%2Fevil.example'))).toBe('/');
    expect(returnPathOf(at('/tasks?project=3'))).toBe('/tasks?project=3');
  });
});

describe('signed-out marker (ADR-0071; also skips the session continuation request)', () => {
  it('absent until sign-out, cleared on signing in again', () => {
    expect(signedOutHere()).toBe(false);
    rememberSignedOut();
    expect(signedOutHere()).toBe(true);
    forgetSilentMarks();
    expect(signedOutHere()).toBe(false);
  });

  it('treated as signed out when unreadable (no request)', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('blocked');
      },
    });
    expect(signedOutHere()).toBe(true);
  });
});
