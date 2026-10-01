import { describe, expect, it } from 'vitest';
import {
  formatOccurrenceTimeRange, formatSegmentTimeRange, groupSegmentsByDate, splitIntoDaySegments,
} from './daySegments';
import { NEW_YORK, TOKYO, hm, occurrence } from './testOccurrences';

const spans = (segments: ReturnType<typeof splitIntoDaySegments>) =>
  segments.map((s) => [s.date, s.startMinute, s.endMinute]);

describe('splitIntoDaySegments', () => {
  it('その日の中で終わる回は 1 区間', () => {
    const segments = splitIntoDaySegments(occurrence('a', '2026-10-05', hm(9), 60), TOKYO);
    expect(spans(segments)).toEqual([['2026-10-05', 540, 600]]);
    expect(segments[0].continuesFromPreviousDay).toBe(false);
    expect(segments[0].continuesToNextDay).toBe(false);
  });

  it('日をまたぐ回はローカル 0:00 で割り、続きを翌日に置く', () => {
    const segments = splitIntoDaySegments(occurrence('a', '2026-10-05', hm(22), 240), TOKYO);
    expect(spans(segments)).toEqual([['2026-10-05', 1320, 1440], ['2026-10-06', 0, 120]]);
    expect(segments[0].continuesToNextDay).toBe(true);
    expect(segments[1].continuesFromPreviousDay).toBe(true);
    expect(formatSegmentTimeRange(segments[0])).toBe('22:00 – 24:00');
    expect(formatSegmentTimeRange(segments[1])).toBe('00:00 – 02:00');
  });

  it('ちょうど翌 0:00 に終わる回は翌日に区間を作らない', () => {
    const segments = splitIntoDaySegments(occurrence('a', '2026-10-05', hm(22), 120), TOKYO);
    expect(spans(segments)).toEqual([['2026-10-05', 1320, 1440]]);
    expect(segments[0].continuesToNextDay).toBe(false);
  });

  it('24 時間を超える回は何日でも割る', () => {
    const segments = splitIntoDaySegments(occurrence('a', '2026-10-08', hm(8), 36 * 60), TOKYO);
    expect(spans(segments)).toEqual([
      ['2026-10-08', 480, 1440],
      ['2026-10-09', 0, 1200],
    ]);
    const longer = splitIntoDaySegments(occurrence('b', '2026-10-08', hm(8), 50 * 60), TOKYO);
    expect(spans(longer)).toEqual([
      ['2026-10-08', 480, 1440],
      ['2026-10-09', 0, 1440],
      ['2026-10-10', 0, 600],
    ]);
  });

  it('割り目は閲覧者のタイムゾーンで決まる', () => {
    // 2026-10-05T14:00Z から 2 時間: 東京では 23:00〜翌 1:00、ニューヨークでは 10:00〜12:00。
    const o = { ...occurrence('a', '2026-10-05', 0, 0), start: '2026-10-05T14:00:00Z', duration_minutes: 120, is_all_day: false };
    expect(spans(splitIntoDaySegments(o, TOKYO))).toEqual([['2026-10-05', 1380, 1440], ['2026-10-06', 0, 60]]);
    expect(spans(splitIntoDaySegments(o, NEW_YORK))).toEqual([['2026-10-05', 600, 720]]);
  });

  it('終日は浮いた日で、ゾーンが違ってもずらさない', () => {
    // ニューヨークの終日（その日 0:00 の瞬間）を東京から見ても、同じ日の終日。
    const allDay = occurrence('a', '2026-10-05', 0, 1440, NEW_YORK);
    const segments = splitIntoDaySegments(allDay, TOKYO);
    expect(spans(segments)).toEqual([['2026-10-05', 0, 1440]]);
    expect(segments[0].isAllDay).toBe(true);
    expect(formatOccurrenceTimeRange(allDay, TOKYO)).toBeNull();
  });

  it('長さ 0 の回は開始の位置に 1 区間', () => {
    expect(spans(splitIntoDaySegments(occurrence('a', '2026-10-05', hm(12), 0), TOKYO))).toEqual([['2026-10-05', 720, 720]]);
  });
});

describe('formatOccurrenceTimeRange', () => {
  it('またぐ回は終わりの壁時計、翌 0:00 ちょうどは 24:00', () => {
    expect(formatOccurrenceTimeRange(occurrence('a', '2026-10-05', hm(14, 15), 45), TOKYO)).toBe('14:15 – 15:00');
    expect(formatOccurrenceTimeRange(occurrence('a', '2026-10-05', hm(22), 240), TOKYO)).toBe('22:00 – 02:00');
    expect(formatOccurrenceTimeRange(occurrence('a', '2026-10-05', hm(22), 120), TOKYO)).toBe('22:00 – 24:00');
  });
});

describe('groupSegmentsByDate', () => {
  it('日ごとに束ね、終日を先・あとは開始の順に並べる', () => {
    const byDate = groupSegmentsByDate([
      occurrence('late', '2026-10-05', hm(15), 60),
      occurrence('overnight', '2026-10-04', hm(23), 120),
      occurrence('allday', '2026-10-05', 0, 1440),
      occurrence('early', '2026-10-05', hm(8), 30),
    ], TOKYO);
    expect(byDate.get('2026-10-05')?.map((s) => s.occurrence.id)).toEqual(['allday', 'overnight', 'early', 'late']);
    expect(byDate.get('2026-10-04')?.map((s) => s.occurrence.id)).toEqual(['overnight']);
  });
});
