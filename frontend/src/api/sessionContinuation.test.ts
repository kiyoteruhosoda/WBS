import { describe, expect, it, vi } from 'vitest';
import type { RenewalResult } from '../auth/silentRenewal';
import { continueSession, type ContinuationSteps } from './sessionContinuation';

const steps = (overrides: Partial<ContinuationSteps> = {}): ContinuationSteps => ({
  signedOutHere: () => false,
  oneAtATime: (task) => task(),
  stillSignedIn: async () => false,
  renewInFrame: async (): Promise<RenewalResult> => 'renewed',
  onRenewed: vi.fn(),
  onDeclined: vi.fn(),
  ...overrides,
});

describe('continueSession', () => {
  it('continues when the IdP allows it', async () => {
    const given = steps();
    expect(await continueSession(given)).toEqual({ kind: 'continued' });
    expect(given.onRenewed).toHaveBeenCalled();
  });

  it('does not ask after sign-out', async () => {
    const renew = vi.fn(async (): Promise<RenewalResult> => 'renewed');
    expect(await continueSession(steps({ signedOutHere: () => true, renewInFrame: renew }))).toEqual({
      kind: 'ended',
    });
    expect(renew).not.toHaveBeenCalled();
  });

  it('does not open the frame when another tab continued while waiting', async () => {
    const renew = vi.fn(async (): Promise<RenewalResult> => 'renewed');
    expect(await continueSession(steps({ stillSignedIn: async () => true, renewInFrame: renew }))).toEqual({
      kind: 'continued',
    });
    expect(renew).not.toHaveBeenCalled();
  });

  it('ends on refusal and does not repeat the silent check in this tab', async () => {
    const given = steps({ renewInFrame: async () => 'declined' });
    expect(await continueSession(given)).toEqual({ kind: 'ended' });
    expect(given.onDeclined).toHaveBeenCalled();
  });

  it('ends when the round trip breaks (without setting the silent-check marker)', async () => {
    const given = steps({ renewInFrame: async () => 'failed' });
    expect(await continueSession(given)).toEqual({ kind: 'ended' });
    expect(given.onDeclined).not.toHaveBeenCalled();
  });

  it('does not treat an unreachable server as signed out', async () => {
    const offline = new Error('Network Error');
    const outcome = await continueSession(
      steps({
        stillSignedIn: async () => {
          throw offline;
        },
      }),
    );
    expect(outcome).toEqual({ kind: 'unavailable', error: offline });
  });

  it('checks within the one-at-a-time queue', async () => {
    const order: string[] = [];
    await continueSession(
      steps({
        oneAtATime: async (task) => {
          order.push('lock');
          return task();
        },
        stillSignedIn: async () => {
          order.push('me');
          return false;
        },
      }),
    );
    expect(order).toEqual(['lock', 'me']);
  });
});
