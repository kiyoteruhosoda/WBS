import { describe, expect, it } from 'vitest';
import { RENEWAL_RESULT_PATH, resultOf } from './silentRenewal';

/** Tests run in node, so the frame is replaced by an object holding only its location */
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
  it('undecided while still in progress', () => {
    expect(resultOf(frameAt(null))).toBeNull();
  });

  it('reads result from the result page', () => {
    expect(resultOf(frameAt(`${RENEWAL_RESULT_PATH}?result=renewed`))).toBe('renewed');
    expect(resultOf(frameAt(`${RENEWAL_RESULT_PATH}?result=declined`))).toBe('declined');
  });

  it('unknown values, other pages and unreadable origins are failed', () => {
    expect(resultOf(frameAt(`${RENEWAL_RESULT_PATH}?result=maybe`))).toBe('failed');
    expect(resultOf(frameAt('/login'))).toBe('failed');
    expect(resultOf(frameAt('https://identity.example.com/authorize', false))).toBe('failed');
  });
});
