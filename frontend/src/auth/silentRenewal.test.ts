import { describe, expect, it } from 'vitest';
import { RENEWAL_RESULT_PATH, resultOf } from './silentRenewal';

/** 試験は node で走るので、枠の行き先だけを持つ形で代える */
const frameAt = (href: string | null, readable = true): HTMLIFrameElement => {
  const url = href === null ? null : new URL(href, 'https://wbs.example.com');
  const contentWindow = {
    get location() {
      if (!readable) throw new DOMException('cross-origin', 'SecurityError');
      return url === null
        ? { href: 'about:blank', pathname: 'blank', search: '' }
        : { href: url.href, pathname: url.pathname, search: url.search };
    },
  };
  return { contentWindow } as unknown as HTMLIFrameElement;
};

describe('resultOf', () => {
  it('まだ途中なら決めない', () => {
    expect(resultOf(frameAt(null))).toBeNull();
  });

  it('結果の頁の result を読む', () => {
    expect(resultOf(frameAt(`${RENEWAL_RESULT_PATH}?result=renewed`))).toBe('renewed');
    expect(resultOf(frameAt(`${RENEWAL_RESULT_PATH}?result=declined`))).toBe('declined');
  });

  it('知らない値・ほかの頁・読めないオリジンは failed', () => {
    expect(resultOf(frameAt(`${RENEWAL_RESULT_PATH}?result=maybe`))).toBe('failed');
    expect(resultOf(frameAt('/login'))).toBe('failed');
    expect(resultOf(frameAt('https://identity.example.com/authorize', false))).toBe('failed');
  });
});
