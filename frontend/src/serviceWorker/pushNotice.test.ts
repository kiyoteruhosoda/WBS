import { describe, expect, it } from 'vitest';
import {
  ALARM_SOUND_CACHE, ALARM_SOUND_KEY, ALARM_SOUND_OFF, FALLBACK_TITLE, HOME_PATH, isSilenced, parsePushPayload, safeAppPath,
} from './pushNotice';
import * as alarmSound from '../preferences/alarmSound';

describe('通知の中身', () => {
  it('サーバの JSON をそのまま読む', () => {
    const notice = parsePushPayload(JSON.stringify({
      title: '設計レビュー', body: '15 分後に始まります', url: '/calendar', tag: 'event_alarm:12:x:15', kind: 'event_alarm',
    }));
    expect(notice).toEqual({
      title: '設計レビュー', body: '15 分後に始まります', url: '/calendar', tag: 'event_alarm:12:x:15', kind: 'event_alarm',
    });
  });

  it('壊れていても空でも通知は出す（既定の題・行き先は今日）', () => {
    expect(parsePushPayload(null)).toEqual({ title: FALLBACK_TITLE, body: '', url: HOME_PATH, tag: undefined, kind: undefined });
    expect(parsePushPayload('ただの文字')).toEqual({ title: FALLBACK_TITLE, body: 'ただの文字', url: HOME_PATH, tag: undefined, kind: undefined });
    expect(parsePushPayload('[1,2]').title).toBe(FALLBACK_TITLE);
    expect(parsePushPayload(JSON.stringify({ title: 3, url: 5 }))).toEqual({ title: FALLBACK_TITLE, body: '', url: HOME_PATH, tag: undefined, kind: undefined });
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

describe('予定の通知の音（task #520）', () => {
  it('消してあれば予定の通知だけ音なしにする', () => {
    expect(isSilenced({ kind: 'event_alarm' }, ALARM_SOUND_OFF)).toBe(true);
    expect(isSilenced({ kind: 'event_alarm' }, 'on')).toBe(false);
    expect(isSilenced({ kind: 'event_alarm' }, null)).toBe(false);
    expect(isSilenced({ kind: 'timer_left_running' }, ALARM_SOUND_OFF)).toBe(false);
    expect(isSilenced({ kind: undefined }, ALARM_SOUND_OFF)).toBe(false);
  });

  it('画面と Service Worker で置き場の名前がそろっている', () => {
    expect(alarmSound.ALARM_SOUND_CACHE).toBe(ALARM_SOUND_CACHE);
    expect(alarmSound.ALARM_SOUND_KEY).toBe(ALARM_SOUND_KEY);
    expect(alarmSound.ALARM_SOUND_OFF).toBe(ALARM_SOUND_OFF);
  });
});
