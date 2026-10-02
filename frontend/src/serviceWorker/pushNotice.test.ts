import { describe, expect, it } from 'vitest';
import { FALLBACK_TITLE, HOME_PATH, parsePushPayload, safeAppPath } from './pushNotice';

describe('通知の中身', () => {
  it('サーバの JSON をそのまま読む', () => {
    const notice = parsePushPayload(JSON.stringify({
      title: '設計レビュー', body: '15 分後に始まります', url: '/calendar', tag: 'event_alarm:12:x:15', kind: 'event_alarm',
    }));
    expect(notice).toEqual({ title: '設計レビュー', body: '15 分後に始まります', url: '/calendar', tag: 'event_alarm:12:x:15' });
  });

  it('壊れていても空でも通知は出す（既定の題・行き先は今日）', () => {
    expect(parsePushPayload(null)).toEqual({ title: FALLBACK_TITLE, body: '', url: HOME_PATH, tag: undefined });
    expect(parsePushPayload('ただの文字')).toEqual({ title: FALLBACK_TITLE, body: 'ただの文字', url: HOME_PATH, tag: undefined });
    expect(parsePushPayload('[1,2]').title).toBe(FALLBACK_TITLE);
    expect(parsePushPayload(JSON.stringify({ title: 3, url: 5 }))).toEqual({ title: FALLBACK_TITLE, body: '', url: HOME_PATH, tag: undefined });
  });
});

describe('押したときに開く先', () => {
  it('このアプリの中のパスだけ通す', () => {
    expect(safeAppPath('/closing?period=2026-10-01')).toBe('/closing?period=2026-10-01');
    expect(safeAppPath('/')).toBe('/');
  });

  it('よそのサイト・壊れた値は今日へ', () => {
    for (const value of ['https://evil.example/', '//evil.example/x', '/\\evil.example', 'javascript:alert(1)', 'calendar', '', null, 3]) {
      expect(safeAppPath(value)).toBe(HOME_PATH);
    }
  });
});
