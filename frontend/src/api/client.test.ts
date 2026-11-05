import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import type { RenewalResult } from '../auth/silentRenewal';

// 見えない枠は DOM が要るので代える（試験は node で走る）。1 本ずつの錠はそのまま走らせる
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

/** 経路ごとの答えを順に返す。尽きたら最後の答えを返し続ける */
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

describe('401 のとき見えない枠で続ける（ADR-0071）', () => {
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

  it('続けられたら元の要求をやり直し、ログイン切れにしない', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/me': [401] });
    await expect(client.get('/tasks')).resolves.toMatchObject({ status: 200 });
    expect(calls).toEqual(['/tasks', '/auth/me', '/tasks']);
    expect(renewInFrame).toHaveBeenCalledTimes(1);
    expect(expired).not.toHaveBeenCalled();
  });

  it('更新の口はもう叩かない', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/me': [401] });
    await client.get('/tasks');
    expect(calls).not.toContain('/auth/refresh');
  });

  it('ほかのタブが先に続けていれば、枠を開かずにやり直す', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/me': [200] });
    await expect(client.get('/tasks')).resolves.toMatchObject({ status: 200 });
    expect(calls).toEqual(['/tasks', '/auth/me', '/tasks']);
    expect(renewInFrame).not.toHaveBeenCalled();
  });

  it('同時に 401 になった要求は 1 本の往復を待つ', async () => {
    fake({ '/a': [401, 200], '/b': [401, 200], '/c': [401, 200], '/auth/me': [401] });
    await Promise.all([client.get('/a'), client.get('/b'), client.get('/c')]);
    expect(renewInFrame).toHaveBeenCalledTimes(1);
  });

  it.each(['declined', 'failed'] as const)('%s ならログイン切れにする', async (result) => {
    renewInFrame.mockImplementation(async () => result);
    const calls = fake({ '/tasks': [401], '/auth/me': [401] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 401 } });
    expect(calls).toEqual(['/tasks', '/auth/me']);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('断られたら、このタブではログイン画面の黙った確かめを重ねない', async () => {
    renewInFrame.mockImplementation(async () => 'declined');
    fake({ '/tasks': [401], '/auth/me': [401] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(sessionStorage.getItem('wbs.sso.silentAttempted')).toBe('1');
  });

  it('やり直しも 401 ならログイン切れにし、もう続けない', async () => {
    const calls = fake({ '/tasks': [401], '/auth/me': [401] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 401 } });
    expect(calls).toEqual(['/tasks', '/auth/me', '/tasks']);
    expect(renewInFrame).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('サインアウトした後は問い合わせない', async () => {
    localStorage.setItem('wbs.sso.signedOut', '1');
    fake({ '/tasks': [401] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(renewInFrame).not.toHaveBeenCalled();
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it.each([503, 'no-response'] as const)('確かめの口が %s のときはログイン切れにしない', async (answer) => {
    fake({ '/tasks': [401], '/auth/me': [answer] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(expired).not.toHaveBeenCalled();
    expect(renewInFrame).not.toHaveBeenCalled();
  });

  it('確かめの口が 503 のときは 503 として失敗を返す（画面がログイン切れと取り違えない）', async () => {
    fake({ '/tasks': [401], '/auth/me': [503] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 503 } });
  });

  it('401 以外の失敗では続けない', async () => {
    const calls = fake({ '/tasks': [500] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 500 } });
    expect(calls).toEqual(['/tasks']);
  });
});
