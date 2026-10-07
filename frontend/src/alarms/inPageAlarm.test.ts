import { describe, expect, it } from 'vitest';
import type { CalendarAlarm } from '../api/calendar';
import type { PushDevice } from '../api/push';
import {
  DUE_GRACE_MS, RUNG_KEEP_MS, alarmWindow, blinkingTitle, claimRing, dueAlarms, isDue, noticeLead,
  parseRungLog, pushCoversAlarms, withNotice,
} from './inPageAlarm';

const AT = Date.parse('2026-10-07T00:45:00Z');

const alarm = (minutesBefore: number, over: Partial<CalendarAlarm> = {}): CalendarAlarm => {
  const startsAt = '2026-10-07T01:00:00Z';
  return {
    id: `12:${startsAt}:${minutesBefore}`,
    occurrence_id: `12:${startsAt}`,
    event_id: 12,
    title: '設計レビュー',
    location: null,
    task_id: null,
    task_title: null,
    starts_at: startsAt,
    duration_minutes: 60,
    notify_at: new Date(Date.parse(startsAt) - minutesBefore * 60_000).toISOString(),
    minutes_before: minutesBefore,
    is_recurring: false,
    ...over,
  };
};

describe('鳴らす時刻（ADR-0021 の規則）', () => {
  it('notify_at より早くは鳴らさない', () => {
    expect(isDue(alarm(15), AT - 1)).toBe(false);
  });

  it('notify_at ちょうどから 1 分の遅れまでは鳴らす', () => {
    expect(isDue(alarm(15), AT)).toBe(true);
    expect(isDue(alarm(15), AT + 30_000)).toBe(true);
    expect(isDue(alarm(15), AT + DUE_GRACE_MS)).toBe(true);
  });

  it('1 分より遅れたら鳴らさない', () => {
    expect(isDue(alarm(15), AT + DUE_GRACE_MS + 1)).toBe(false);
  });

  it('引く期間は「今 − 1 分」から先へ', () => {
    const { from, to } = alarmWindow(AT);
    expect(from).toBe('2026-10-07T00:44:00.000Z');
    expect(Date.parse(to)).toBeGreaterThan(AT);
  });

  it('この画面でもう出したものは除く', () => {
    const list = [alarm(15), alarm(5)];
    expect(dueAlarms(list, AT, new Set()).map((a) => a.minutes_before)).toEqual([15]);
    expect(dueAlarms(list, AT, new Set([alarm(15).id]))).toEqual([]);
  });
});

describe('出している知らせ', () => {
  it('同じ回の前の知らせは新しいものに置き換える', () => {
    const shown = withNotice([alarm(15)], alarm(5));
    expect(shown.map((a) => a.minutes_before)).toEqual([5]);
  });

  it('別の回の知らせは並べる', () => {
    const other = alarm(5, { id: '13:x:5', occurrence_id: '13:x' });
    expect(withNotice([alarm(15)], other)).toHaveLength(2);
  });

  it('文言は何分前か・開始時刻か', () => {
    expect(noticeLead(alarm(15))).toEqual({ key: 'inPageAlarm.startsIn', params: { minutes: 15 } });
    expect(noticeLead(alarm(0)).key).toBe('inPageAlarm.startsNow');
  });

  it('タブの題名は拍ごとに入れ替わる', () => {
    expect(blinkingTitle('WBS', '🔔 設計レビュー', 0)).toBe('🔔 設計レビュー');
    expect(blinkingTitle('WBS', '🔔 設計レビュー', 1)).toBe('WBS');
  });
});

describe('タブを複数開いていても 1 回だけ鳴らす', () => {
  it('最初に取ったタブだけが鳴らす', () => {
    const first = claimRing({}, alarm(15).id, AT);
    expect(first.claimed).toBe(true);
    const second = claimRing(first.log, alarm(15).id, AT + 1000);
    expect(second.claimed).toBe(false);
  });

  it('古い印は捨てる', () => {
    const { log } = claimRing({ old: AT - RUNG_KEEP_MS }, alarm(15).id, AT);
    expect(Object.keys(log)).toEqual([alarm(15).id]);
  });

  it('読めない印は空とみなす', () => {
    expect(parseRungLog(null)).toEqual({});
    expect(parseRungLog('{')).toEqual({});
    expect(parseRungLog('[1]')).toEqual({});
    expect(parseRungLog('{"a":1,"b":"x"}')).toEqual({ a: 1 });
  });
});

describe('Web Push で受け取っている端末では鳴らさない', () => {
  const device = (over: Partial<PushDevice> = {}): PushDevice => ({
    id: 1, endpoint: 'https://push/1', label: 'Chrome', receives_calendar: true,
    created_at: null, last_sent_at: null, ...over,
  });
  const base = { serverEnabled: true, endpoint: 'https://push/1', devices: [device()], eventAlarm: true };

  it('この端末の購読が予定の通知を受けていれば受け取っている', () => {
    expect(pushCoversAlarms(base)).toBe(true);
  });

  it('どれか 1 つ欠ければ受け取っていない（画面の中で鳴らす）', () => {
    expect(pushCoversAlarms({ ...base, serverEnabled: false })).toBe(false);
    expect(pushCoversAlarms({ ...base, endpoint: null })).toBe(false);
    expect(pushCoversAlarms({ ...base, eventAlarm: false })).toBe(false);
    expect(pushCoversAlarms({ ...base, devices: [device({ receives_calendar: false })] })).toBe(false);
    // 別の端末から外した（ブラウザに購読は残るがサーバの一覧に無い）
    expect(pushCoversAlarms({ ...base, devices: [device({ endpoint: 'https://push/2' })] })).toBe(false);
  });
});
