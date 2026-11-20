import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  PROBE_PATH,
  checkService,
  currentOutage,
  outageFrom,
  reportOutage,
  resetOutageForTests,
  subscribeOutage,
} from './maintenance';

const json = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('outageFrom', () => {
  it('reads the edge maintenance answer', () => {
    expect(
      outageFrom(503, {
        error: 'service_unavailable',
        reason: 'maintenance',
        until: '2026-11-20T10:00:00Z',
        message: 'Release',
        title: 'Down for a moment',
        body: 'Back soon',
      }),
    ).toEqual({
      reason: 'maintenance',
      until: '2026-11-20T10:00:00Z',
      message: 'Release',
      title: 'Down for a moment',
      body: 'Back soon',
    });
  });

  it('reads "stopped" and treats empty text as missing', () => {
    expect(outageFrom(503, { error: 'service_unavailable', reason: 'stopped', title: ' ', host: 'x' })).toEqual({
      reason: 'stopped',
      title: null,
      body: null,
      message: null,
      until: null,
    });
  });

  it.each([
    ['another status', 500, { error: 'service_unavailable', reason: 'maintenance' }],
    ["the app's own error", 503, { detail: { error: 'service_unavailable' } }],
    ['an unknown reason', 503, { error: 'service_unavailable', reason: 'busy' }],
    ['no body', 503, null],
    ['a text body', 503, '<html>'],
  ])('ignores %s', (_label, status, body) => {
    expect(outageFrom(status, body)).toBeNull();
  });
});

describe('checkService', () => {
  afterEach(() => {
    resetOutageForTests();
  });

  it('stays closed while the edge still answers maintenance, without a stored answer', async () => {
    const fetcher = vi.fn<typeof fetch>(async () => json(503, { error: 'service_unavailable', reason: 'maintenance' }));
    await expect(checkService(fetcher)).resolves.toBe('closed');
    expect(currentOutage()?.reason).toBe('maintenance');
    expect(fetcher).toHaveBeenCalledWith(PROBE_PATH, { cache: 'no-store', credentials: 'same-origin' });
  });

  it.each([200, 401, 404])('opens on %s (the edge let it through)', async (status) => {
    reportOutage({ reason: 'maintenance', title: null, body: null, message: null, until: null });
    const listener = vi.fn();
    subscribeOutage(listener);
    await expect(checkService(async () => json(status, {}))).resolves.toBe('open');
    expect(currentOutage()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('keeps the state when unreachable or on another server failure', async () => {
    reportOutage({ reason: 'maintenance', title: null, body: null, message: null, until: null });
    await expect(
      checkService(async () => {
        throw new TypeError('Failed to fetch');
      }),
    ).resolves.toBe('unknown');
    await expect(checkService(async () => new Response('<html>', { status: 502 }))).resolves.toBe('unknown');
    expect(currentOutage()).not.toBeNull();
  });
});
