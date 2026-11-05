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
  it('IdP が続けてよいと答えたら続ける', async () => {
    const given = steps();
    expect(await continueSession(given)).toEqual({ kind: 'continued' });
    expect(given.onRenewed).toHaveBeenCalled();
  });

  it('サインアウトした後は問い合わせない', async () => {
    const renew = vi.fn(async (): Promise<RenewalResult> => 'renewed');
    expect(await continueSession(steps({ signedOutHere: () => true, renewInFrame: renew }))).toEqual({
      kind: 'ended',
    });
    expect(renew).not.toHaveBeenCalled();
  });

  it('待っている間にほかのタブが続けていれば、枠を開かない', async () => {
    const renew = vi.fn(async (): Promise<RenewalResult> => 'renewed');
    expect(await continueSession(steps({ stillSignedIn: async () => true, renewInFrame: renew }))).toEqual({
      kind: 'continued',
    });
    expect(renew).not.toHaveBeenCalled();
  });

  it('断られたら終わり、このタブでは黙った確かめを重ねない', async () => {
    const given = steps({ renewInFrame: async () => 'declined' });
    expect(await continueSession(given)).toEqual({ kind: 'ended' });
    expect(given.onDeclined).toHaveBeenCalled();
  });

  it('往復が壊れたら終わる（黙った確かめの印は付けない）', async () => {
    const given = steps({ renewInFrame: async () => 'failed' });
    expect(await continueSession(given)).toEqual({ kind: 'ended' });
    expect(given.onDeclined).not.toHaveBeenCalled();
  });

  it('サーバーに届かないときはログアウト扱いにしない', async () => {
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

  it('1 本ずつの順番の中で確かめる', async () => {
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
