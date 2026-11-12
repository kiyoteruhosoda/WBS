import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import type { RenewalResult } from '../auth/silentRenewal';

// The hidden frame needs the DOM, so it is replaced (tests run in node). The one-at-a-time lock runs as is
const { renewInFrame } = vi.hoisted(() => ({
  renewInFrame: vi.fn(async (): Promise<RenewalResult> => 'renewed'),
}));
vi.mock('../auth/silentRenewal', () => ({
  renewInFrame: () => renewInFrame(),
  oneAtATime: <T>(task: () => Promise<T>) => task(),
}));

import client, { setUnauthorizedHandler } from './client';

type Answer = number | 'no-response';

const respond = (config: InternalAxiosRequestConfig, answer: Answer): Promise<AxiosResponse> => {
  if (answer === 'no-response') {
    const error = new Error('Network Error') as AxiosError;
    error.isAxiosError = true;
    error.config = config;
    return Promise.reject(error);
  }
  const response = { data: {}, status: answer, statusText: '', headers: {}, config } as AxiosResponse;
  if (answer < 400) return Promise.resolve(response);
  const error = new Error(`status ${answer}`) as AxiosError;
  error.isAxiosError = true;
  error.config = config;
  error.response = response;
  return Promise.reject(error);
};

/** Returns the answers per path in order; repeats the last one when exhausted */
const fake = (answers: Record<string, Answer[]>) => {
  const calls: string[] = [];
  const adapter: AxiosAdapter = (config) => {
    const url = config.url ?? '';
    calls.push(url);
    const queue = answers[url] ?? [200];
    const answer = queue.length > 1 ? (queue.shift() as Answer) : queue[0];
    return respond(config, answer);
  };
  client.defaults.adapter = adapter;
  return calls;
};

describe('continuing via a hidden frame on 401 (ADR-0071)', () => {
  const expired = vi.fn();
  const storage = () => {
    const values = new Map<string, string>();
    return {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => void values.set(key, value),
      removeItem: (key: string) => void values.delete(key),
    };
  };
  beforeEach(() => {
    setUnauthorizedHandler(expired);
    vi.stubGlobal('localStorage', storage());
    vi.stubGlobal('sessionStorage', storage());
    renewInFrame.mockImplementation(async () => 'renewed');
  });
  afterEach(() => {
    setUnauthorizedHandler(null);
    expired.mockReset();
    renewInFrame.mockReset();
    vi.unstubAllGlobals();
  });

  it('retries the original request after continuing and does not expire the session', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/me': [401] });
    await expect(client.get('/tasks')).resolves.toMatchObject({ status: 200 });
    expect(calls).toEqual(['/tasks', '/auth/me', '/tasks']);
    expect(renewInFrame).toHaveBeenCalledTimes(1);
    expect(expired).not.toHaveBeenCalled();
  });

  it('no longer calls the refresh endpoint', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/me': [401] });
    await client.get('/tasks');
    expect(calls).not.toContain('/auth/refresh');
  });

  it('retries without opening a frame when another tab already continued', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/me': [200] });
    await expect(client.get('/tasks')).resolves.toMatchObject({ status: 200 });
    expect(calls).toEqual(['/tasks', '/auth/me', '/tasks']);
    expect(renewInFrame).not.toHaveBeenCalled();
  });

  it('concurrent 401 requests wait for a single round trip', async () => {
    fake({ '/a': [401, 200], '/b': [401, 200], '/c': [401, 200], '/auth/me': [401] });
    await Promise.all([client.get('/a'), client.get('/b'), client.get('/c')]);
    expect(renewInFrame).toHaveBeenCalledTimes(1);
  });

  it.each(['declined', 'failed'] as const)('expires the session on %s', async (result) => {
    renewInFrame.mockImplementation(async () => result);
    const calls = fake({ '/tasks': [401], '/auth/me': [401] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 401 } });
    expect(calls).toEqual(['/tasks', '/auth/me']);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('after a refusal, the sign-in page does not repeat the silent check in this tab', async () => {
    renewInFrame.mockImplementation(async () => 'declined');
    fake({ '/tasks': [401], '/auth/me': [401] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(sessionStorage.getItem('wbs.sso.silentAttempted')).toBe('1');
  });

  it('expires the session and stops continuing when the retry is also 401', async () => {
    const calls = fake({ '/tasks': [401], '/auth/me': [401] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 401 } });
    expect(calls).toEqual(['/tasks', '/auth/me', '/tasks']);
    expect(renewInFrame).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('does not ask after sign-out', async () => {
    localStorage.setItem('wbs.sso.signedOut', '1');
    fake({ '/tasks': [401] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(renewInFrame).not.toHaveBeenCalled();
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it.each([503, 'no-response'] as const)('does not expire the session when the check endpoint gives %s', async (answer) => {
    fake({ '/tasks': [401], '/auth/me': [answer] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(expired).not.toHaveBeenCalled();
    expect(renewInFrame).not.toHaveBeenCalled();
  });

  it('returns a 503 failure when the check endpoint gives 503 (so the UI doesn't mistake it for expiry)', async () => {
    fake({ '/tasks': [401], '/auth/me': [503] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 503 } });
  });

  it('does not continue on failures other than 401', async () => {
    const calls = fake({ '/tasks': [500] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 500 } });
    expect(calls).toEqual(['/tasks']);
  });
});
