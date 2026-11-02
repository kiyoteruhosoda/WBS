import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
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

describe('401 のときの更新', () => {
  const expired = vi.fn();
  beforeEach(() => setUnauthorizedHandler(expired));
  afterEach(() => {
    setUnauthorizedHandler(null);
    expired.mockReset();
  });

  it('更新できたら元の要求をやり直し、ログイン切れにしない', async () => {
    const calls = fake({ '/tasks': [401, 200], '/auth/refresh': [200] });
    await expect(client.get('/tasks')).resolves.toMatchObject({ status: 200 });
    expect(calls).toEqual(['/tasks', '/auth/refresh', '/tasks']);
    expect(expired).not.toHaveBeenCalled();
  });

  it('同時に 401 になった要求は 1 本の更新を待つ', async () => {
    const calls = fake({
      '/a': [401, 200],
      '/b': [401, 200],
      '/c': [401, 200],
      '/auth/refresh': [200],
    });
    await Promise.all([client.get('/a'), client.get('/b'), client.get('/c')]);
    expect(calls.filter((url) => url === '/auth/refresh')).toHaveLength(1);
  });

  it('更新が断られたらログイン切れにする', async () => {
    const calls = fake({ '/tasks': [401], '/auth/refresh': [401] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 401 } });
    expect(calls).toEqual(['/tasks', '/auth/refresh']);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('やり直しも 401 ならログイン切れにし、もう更新しない', async () => {
    const calls = fake({ '/tasks': [401], '/auth/refresh': [200] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 401 } });
    expect(calls).toEqual(['/tasks', '/auth/refresh', '/tasks']);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it.each([503, 'no-response'] as const)('更新の口が %s のときはログイン切れにしない', async (answer) => {
    fake({ '/tasks': [401], '/auth/refresh': [answer] });
    await expect(client.get('/tasks')).rejects.toBeDefined();
    expect(expired).not.toHaveBeenCalled();
  });

  it('更新の口が 503 のときは 503 として失敗を返す（画面がログイン切れと取り違えない）', async () => {
    fake({ '/tasks': [401], '/auth/refresh': [503] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 503 } });
  });

  it('401 以外の失敗では更新しない', async () => {
    const calls = fake({ '/tasks': [500] });
    await expect(client.get('/tasks')).rejects.toMatchObject({ response: { status: 500 } });
    expect(calls).toEqual(['/tasks']);
  });
});
