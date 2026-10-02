import { describe, expect, it } from 'vitest';
import type { Calendar, DayOffMark } from '../types';
import { buildDayOffView, businessDaysBetween, dayOffLabel, dayOffReasonsOn } from './daysOff';
import { eventColor } from './calendarColors';

const layer = (id: number, patch: Partial<Calendar>): Calendar => ({
  id, kind: 'DAYS_OFF', name: `l${id}`, color_key: 'TOMATO', sort_order: 1000 + id, is_default: false, is_visible: true,
  workdays: null, day_off_reason: 'PERSONAL', counts_as_day_off: true, created_at: null, updated_at: null, ...patch,
});

const calendars: Calendar[] = [
  layer(1, { kind: 'WORKWEEK', name: '営業日', day_off_reason: null, workdays: ['MO', 'TU', 'WE', 'TH', 'FR'], color_key: 'GRAPHITE' }),
  layer(2, { name: '会社の公休', day_off_reason: 'COMPANY', color_key: 'TANGERINE' }),
  layer(3, { name: '私の休み', day_off_reason: 'PERSONAL', color_key: 'SAGE' }),
  layer(4, { name: '日本の祝日', day_off_reason: 'NATIONAL_HOLIDAY', color_key: 'TOMATO' }),
];

const marks: DayOffMark[] = [
  { date: '2026-10-10', reason: 'WEEKLY', calendar_id: 1, name: null, counts_as_day_off: true },
  { date: '2026-10-11', reason: 'WEEKLY', calendar_id: 1, name: null, counts_as_day_off: true },
  { date: '2026-10-12', reason: 'PERSONAL', calendar_id: 3, name: '旅行', counts_as_day_off: true },
  { date: '2026-10-12', reason: 'NATIONAL_HOLIDAY', calendar_id: 4, name: 'スポーツの日', counts_as_day_off: true },
  { date: '2026-10-13', reason: 'PERSONAL', calendar_id: 3, name: null, counts_as_day_off: false },
];

describe('休みの層を重ねる（ADR-0029）', () => {
  it('日に 1 つの帯。理由は強い順に名前をつなぎ、色はいちばん強い層', () => {
    const view = buildDayOffView(marks, calendars);
    expect(view.holidays).toEqual([
      { date: '2026-10-12', name: 'スポーツの日・私の休み: 旅行', reason: 'NATIONAL_HOLIDAY', color: eventColor('TOMATO') },
      { date: '2026-10-13', name: '私の休み', reason: 'PERSONAL', color: eventColor('SAGE') },
    ]);
    expect([...(view.nonWorkdays ?? [])]).toEqual(['2026-10-10', '2026-10-11']);
  });

  it('営業日の判定は表示に関係なく、数える理由で決まる', () => {
    const hidden = calendars.map((c) => ({ ...c, is_visible: false }));
    const view = buildDayOffView(marks, hidden);
    expect(view.holidays).toEqual([]);
    expect(view.nonWorkdays).toBeNull();
    expect([...view.nonBusinessDays].sort()).toEqual(['2026-10-10', '2026-10-11', '2026-10-12']);
    // 10/9(金)〜10/14(水): 9・13・14 の 3 日（13 は数えない層）
    expect(businessDaysBetween('2026-10-09', '2026-10-14', view.nonBusinessDays)).toBe(3);
  });

  it('知らせの文は数える理由だけ', () => {
    expect(dayOffReasonsOn('2026-10-12', marks, calendars, '曜日の休み')).toBe('私の休み: 旅行・スポーツの日');
    expect(dayOffReasonsOn('2026-10-10', marks, calendars, '曜日の休み')).toBe('曜日の休み');
    expect(dayOffReasonsOn('2026-10-13', marks, calendars, '曜日の休み')).toBeNull();
  });

  it('帯の名前', () => {
    expect(dayOffLabel(marks[3], '日本の祝日')).toBe('スポーツの日');
    expect(dayOffLabel(marks[4], '私の休み')).toBe('私の休み');
  });
});
