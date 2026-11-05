// 401 のあとログインを続けるかの決まり（ADR-0071）。DOM に触らない純な手順だけを置く（試験は node で走る）。
//
// 1. サインアウトした印があれば問い合わせない（IdP のログイン状態は既定で残るので、入り直してしまう）
// 2. タブをまたいで 1 本ずつ。順番を待つ間にほかのタブが続けていれば（`/auth/me` が通れば）枠を開かない
// 3. 見えない枠で IdP へ問い合わせる。断られたら、ログイン画面の黙った確かめ（ADR-0062）をこのタブで重ねない
import type { RenewalResult } from '../auth/silentRenewal';

export type ContinuationOutcome =
  | { kind: 'continued' }
  /** 続けられなかった。ログインは終わっている */
  | { kind: 'ended' }
  /** サーバーに届かない。⚠ ログアウト扱いにしない（Cookie は残っていて、戻れば続く） */
  | { kind: 'unavailable'; error: unknown };

export interface ContinuationSteps {
  signedOutHere: () => boolean;
  oneAtATime: <T>(task: () => Promise<T>) => Promise<T>;
  /** 今のログインで通るか。届かなければ投げる */
  stillSignedIn: () => Promise<boolean>;
  renewInFrame: () => Promise<RenewalResult>;
  /** 続けられた。黙った確かめの印を消す */
  onRenewed: () => void;
  /** 断られた。このタブでは黙った確かめをもう試さない */
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
