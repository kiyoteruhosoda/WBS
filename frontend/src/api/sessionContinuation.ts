// Rules for whether to continue the session after a 401 (ADR-0071). Holds only pure steps that don't touch the DOM (tests run in node).
//
// 1. If the signed-out marker is set, don't ask (the IdP session survives by default, so it would sign back in)
// 2. One at a time across tabs. If another tab continued while waiting (`/auth/me` succeeds), don't open the frame
// 3. Ask the IdP in a hidden frame. If refused, the sign-in page's silent check (ADR-0062) is not repeated in this tab
import type { RenewalResult } from '../auth/silentRenewal';

export type ContinuationOutcome =
  | { kind: 'continued' }
  /** Could not continue. The session is over */
  | { kind: 'ended' }
  /** Server unreachable. ⚠ Not treated as signed out (cookies remain and it continues once back) */
  | { kind: 'unavailable'; error: unknown };

export interface ContinuationSteps {
  signedOutHere: () => boolean;
  oneAtATime: <T>(task: () => Promise<T>) => Promise<T>;
  /** Whether the current session works. Throws when unreachable */
  stillSignedIn: () => Promise<boolean>;
  renewInFrame: () => Promise<RenewalResult>;
  /** Continued. Clear the silent-check marker */
  onRenewed: () => void;
  /** Refused. Don't try the silent check again in this tab */
  onDeclined: () => void;
}

export const continueSession = async (steps: ContinuationSteps): Promise<ContinuationOutcome> => {
  if (steps.signedOutHere()) return { kind: 'ended' };
  return steps.oneAtATime(async () => {
    try {
      if (await steps.stillSignedIn()) return { kind: 'continued' } as const;
    } catch (error) {
      return { kind: 'unavailable', error } as const;
    }
    const result = await steps.renewInFrame();
    if (result === 'renewed') {
      steps.onRenewed();
      return { kind: 'continued' } as const;
    }
    if (result === 'declined') steps.onDeclined();
    return { kind: 'ended' } as const;
  });
};
