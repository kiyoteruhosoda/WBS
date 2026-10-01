import { describe, expect, it } from 'vitest';
import type { EventForm } from './eventForm';
import {
  buildAdjustment, buildRecurrence, endOf, endTimeOptions, formFromEvent, newEventForm, parseTime,
  planEventSave, planOccurrenceDelete, startTimeOptions, withEndMinute, withRepeat, withStartMinute,
} from './eventForm';
import { apiOccurrence, recurringEvent, recurringOccurrence, singleEvent } from './calendarFixtures';

// 予定の編集画面（移植元 EventEditViewModel）の入力と、API の応答 → 入力・入力 → API の変換。

const TOKYO = 'Asia/Tokyo';
const TODAY = '2026-05-01';

const fresh = (patch: Partial<EventForm> = {}): EventForm => ({
  ...newEventForm({ date: '2026-05-04', startMinute: 540, timeZone: TOKYO, today: TODAY }),
  title: '打ち合わせ',
  ...patch,
});

describe('新しい予定の中身（InitializeNewEvent）', () => {
  it('開始は 15 分に丸め、長さは 30 分。繰り返しの選び方は開始日（月曜・第 1 週・5 月 4 日）に合わせる', () => {
    const form = newEventForm({ date: '2026-05-04', startMinute: 607, timeZone: TOKYO, today: TODAY });
    expect(form).toMatchObject({
      startDate: '2026-05-04', startMinute: 600, durationMinutes: 30, allDay: false, repeat: 'NONE',
      weekdays: ['MO'], dayOfMonth: 4, monthlyWeekday: 'MO', monthlyWeekIndex: 1, yearlyMonth: 5, yearlyDay: 4,
      hasEndDate: false, endDate: '2027-05-01', colorKey: 'DEFAULT', taskId: null, timeZone: TOKYO,
    });
  });

  it('時刻を渡さなければ 9:00、ドラッグの範囲を渡せばその終わりまで（最短 15 分）', () => {
    expect(newEventForm({ date: '2026-05-04', timeZone: TOKYO, today: TODAY }).startMinute).toBe(540);
    expect(newEventForm({ date: '2026-05-04', startMinute: 540, endMinute: 660, timeZone: TOKYO, today: TODAY }).durationMinutes).toBe(120);
    expect(newEventForm({ date: '2026-05-04', startMinute: 540, endMinute: 545, timeZone: TOKYO, today: TODAY }).durationMinutes).toBe(15);
  });

  it('夜遅くに作ると、終わりはその日の 24:00 で止める', () => {
    const form = newEventForm({ date: '2026-05-04', startMinute: 1430, timeZone: TOKYO, today: TODAY });
    expect(form.startMinute).toBe(1425);
    expect(endOf(form)).toEqual({ minute: 1440, dayOffset: 0 });
  });

  it('営業日カレンダーが 1 つだけなら最初から選んでおく', () => {
    expect(newEventForm({ date: '2026-05-04', timeZone: TOKYO, today: TODAY, calendarIds: [3] }).adjustmentCalendarId).toBe(3);
    expect(newEventForm({ date: '2026-05-04', timeZone: TOKYO, today: TODAY, calendarIds: [3, 4] }).adjustmentCalendarId).toBeNull();
  });
});

describe('開始・終了の時刻', () => {
  it('終了の候補は 15 分おきの末尾に 24:00。刻みから外れた今の値は差し込む', () => {
    const ends = endTimeOptions(600);
    expect(ends).toHaveLength(97);
    expect(ends[ends.length - 1]).toBe(1440);
    expect(endTimeOptions(610)).toContain(610);
    const starts = startTimeOptions(0);
    expect(starts).toHaveLength(96);
    expect(starts[starts.length - 1]).toBe(1425);
  });

  it('終了の壁時計: ちょうど翌 0:00 は 24:00、日をまたげば何日後か', () => {
    expect(endOf({ startMinute: 0, durationMinutes: 1440 })).toEqual({ minute: 1440, dayOffset: 0 });
    expect(endOf({ startMinute: 1320, durationMinutes: 240 })).toEqual({ minute: 120, dayOffset: 1 });
    expect(endOf({ startMinute: 480, durationMinutes: 36 * 60 })).toEqual({ minute: 1200, dayOffset: 1 });
  });

  it('終了に 24:00 を選べばその日の終わりまで、開始より前を選べば翌日のその時刻まで', () => {
    expect(withEndMinute(fresh({ startMinute: 600 }), 1440).durationMinutes).toBe(840);
    expect(withEndMinute(fresh({ startMinute: 1320 }), 120).durationMinutes).toBe(240);
  });

  it('開始を動かしても長さはそのまま（SetStartTimePreservingDuration）', () => {
    const form = withStartMinute(fresh({ startMinute: 540, durationMinutes: 90 }), 600);
    expect(endOf(form)).toEqual({ minute: 690, dayOffset: 0 });
  });

  it('HH:MM を読む（24:00 まで）', () => {
    expect(parseTime('9:30')).toBe(570);
    expect(parseTime('24:00')).toBe(1440);
    expect(parseTime('24:30')).toBeNull();
    expect(parseTime('12:60')).toBeNull();
    expect(parseTime('noon')).toBeNull();
  });
});

describe('API の応答 → 入力（LoadEvent）', () => {
  it('単発: 予定のタイムゾーンの壁時計で開始日・時刻を出し、詳細と色・タスクを写す', () => {
    const { form, context } = formFromEvent(singleEvent(), apiOccurrence(), TODAY);
    expect(form).toMatchObject({
      title: '設計レビュー', location: '会議室A', memo: '資料は前日まで', timeZone: TOKYO,
      startDate: '2026-05-04', startMinute: 540, durationMinutes: 60, allDay: false, repeat: 'NONE',
      colorKey: 'TOMATO', taskId: 12,
    });
    expect(context).toMatchObject({ mode: 'edit', isMovedOccurrence: false });
  });

  it('終日の回は浮いた日（回の date）のまま', () => {
    const event = singleEvent({ start: '2026-05-03T15:00:00Z', duration_minutes: 1440 });
    const occurrence = apiOccurrence({ start: '2026-05-03T15:00:00Z', duration_minutes: 1440, is_all_day: true, date: '2026-05-04' });
    expect(formFromEvent(event, occurrence, TODAY).form).toMatchObject({ allDay: true, startDate: '2026-05-04' });
  });

  it('繰り返し: 回の位置を開始に出し、規則（第 2 火曜・隔月・終了日・祝日なら前の営業日）を入力へ戻す', () => {
    const { form } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    expect(form).toMatchObject({
      startDate: '2026-07-14', startMinute: 600, durationMinutes: 30, repeat: 'MONTHLY',
      monthlyKind: 'NTH_WEEKDAY', monthlyWeekIndex: 2, monthlyWeekday: 'TU',
      useCustomInterval: true, interval: 2, hasEndDate: true, endDate: '2026-12-31',
      useAdjustment: true, adjustmentDateType: 'SCHEDULED', adjustmentDirection: 'BEFORE', adjustmentDays: 1,
      adjustmentCalendarId: 3,
    });
    // 入力 → 規則で元の規則に戻る（読み込みと組み立てが対になっている）
    expect(buildRecurrence(form)).toEqual(recurringEvent().recurrence);
  });

  it('振替の回は単発として見せる（繰り返しは「なし」・範囲は聞かない）', () => {
    const moved = recurringOccurrence({ is_moved: true, start: '2026-07-15T05:00:00Z', date: '2026-07-15' });
    const { form, context } = formFromEvent(recurringEvent(), moved, TODAY);
    expect(form).toMatchObject({ repeat: 'NONE', startDate: '2026-07-15', startMinute: 840 });
    expect(context).toMatchObject({ isMovedOccurrence: true });
  });
});

describe('入力 → 繰り返しの規則（BuildRecurrenceRule）', () => {
  it('繰り返しの種類を「なし」から選んだときだけ、開始日に合わせる', () => {
    const weekly = withRepeat(fresh({ startDate: '2026-05-06' }), 'WEEKLY');
    expect(weekly.weekdays).toEqual(['WE']);
    const monthly = withRepeat({ ...weekly, weekdays: ['MO', 'FR'] }, 'MONTHLY');
    expect(monthly.weekdays).toEqual(['MO', 'FR']);
  });

  it('毎週: 曜日は日曜始まりの順。間隔を指定しなければ 1、終了日を指定しなければ null', () => {
    const form = fresh({ repeat: 'WEEKLY', weekdays: ['FR', 'MO'], interval: 3, useCustomInterval: false });
    expect(buildRecurrence(form)).toEqual({
      type: 'WEEKLY', interval: 1, end_date: null, weekly: { weekdays: ['MO', 'FR'] }, monthly: null, yearly: null, adjustment: null,
    });
  });

  it('毎月: ○日・月末・第 n 曜日（最終は -1）', () => {
    expect(buildRecurrence(fresh({ repeat: 'MONTHLY', dayOfMonth: 25 }))?.monthly).toEqual({ kind: 'DAY_OF_MONTH', day: 25 });
    expect(buildRecurrence(fresh({ repeat: 'MONTHLY', monthlyLastDay: true }))?.monthly).toEqual({ kind: 'LAST_DAY' });
    expect(buildRecurrence(fresh({ repeat: 'MONTHLY', monthlyKind: 'NTH_WEEKDAY', monthlyWeekIndex: -1, monthlyWeekday: 'FR' }))?.monthly)
      .toEqual({ kind: 'NTH_WEEKDAY', week_index: -1, weekday: 'FR' });
  });

  it('毎年: 月日・第 n 曜日。間隔と終了日も載せる', () => {
    expect(buildRecurrence(fresh({
      repeat: 'YEARLY', yearlyKind: 'NTH_WEEKDAY', yearlyMonth: 1, yearlyWeekIndex: 2, yearlyWeekday: 'MO',
      useCustomInterval: true, interval: 2, hasEndDate: true, endDate: '2030-12-31',
    }))).toMatchObject({
      type: 'YEARLY', interval: 2, end_date: '2030-12-31', yearly: { kind: 'NTH_WEEKDAY', month: 1, week_index: 2, weekday: 'MO' },
    });
  });

  it('営業日シフト: 予定日は祝日のときだけ（キャンセルも選べる）、基準日は常に N 営業日', () => {
    expect(buildAdjustment(fresh({ useAdjustment: false }))).toBeNull();
    expect(buildAdjustment(fresh({ useAdjustment: true, adjustmentDirection: 'CANCEL', adjustmentCalendarId: 3 }))).toEqual({
      condition: 'HOLIDAY', shift_unit: 'BUSINESS_DAY', shift_amount: 0, calendar_id: 3, action: 'CANCEL',
    });
    expect(buildAdjustment(fresh({ useAdjustment: true, adjustmentDateType: 'BASE', adjustmentDirection: 'AFTER', adjustmentDays: 3 }))).toEqual({
      condition: 'ALWAYS', shift_unit: 'BUSINESS_DAY', shift_amount: 3, calendar_id: null, action: 'SHIFT',
    });
    expect(buildAdjustment(fresh({ useAdjustment: true, adjustmentDateType: 'BASE', adjustmentDays: 0 }))).toBeNull();
  });
});

describe('保存 → API の呼び出し', () => {
  it('新しい単発: 閲覧者のタイムゾーンの壁時計を UTC の瞬間へ直して作る', () => {
    expect(planEventSave(fresh(), { mode: 'create' }, null)).toEqual({
      kind: 'requests',
      requests: [{
        method: 'POST',
        url: '/calendar/events',
        body: {
          title: '打ち合わせ', location: null, description: null, color_key: 'DEFAULT', task_id: null,
          time_zone: TOKYO, start: '2026-05-04T00:00:00.000Z', duration_minutes: 30, recurrence: null,
        },
      }],
    });
  });

  it('終日は 0:00 から 1440 分', () => {
    const plan = planEventSave(fresh({ allDay: true }), { mode: 'create' }, null);
    expect(plan).toMatchObject({ requests: [{ body: { start: '2026-05-03T15:00:00.000Z', duration_minutes: 1440 } }] });
  });

  it('入力の誤り: タイトルなし・曜日なし・終了日が開始より前', () => {
    expect(planEventSave(fresh({ title: '  ' }), { mode: 'create' }, null)).toEqual({ kind: 'invalid', error: 'titleRequired' });
    expect(planEventSave(fresh({ repeat: 'WEEKLY', weekdays: [] }), { mode: 'create' }, null)).toEqual({ kind: 'invalid', error: 'weekdayRequired' });
    expect(planEventSave(fresh({ repeat: 'WEEKLY', hasEndDate: true, endDate: '2026-05-01' }), { mode: 'create' }, null))
      .toEqual({ kind: 'invalid', error: 'endDateBeforeStart' });
  });

  it('単発の編集: 詳細と日時を置き換える（版は読んだ予定の版）', () => {
    const { form, context } = formFromEvent(singleEvent(), apiOccurrence(), TODAY);
    expect(planEventSave(withStartMinute(form, 600), context, null)).toEqual({
      kind: 'requests',
      requests: [{
        method: 'PUT',
        url: '/calendar/events/5',
        body: {
          title: '設計レビュー', location: '会議室A', description: '資料は前日まで', color_key: 'TOMATO', task_id: 12,
          start: '2026-05-04T01:00:00.000Z', duration_minutes: 60, expected_version: 3,
        },
      }],
    });
  });

  it('繰り返しの回から開いたら、範囲を聞くまで送らない', () => {
    const { form, context } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    expect(planEventSave(form, context, null)).toEqual({ kind: 'needsScope' });
  });

  it('この予定のみ: 回の鍵を返して単発に切り出す', () => {
    const { form, context } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    expect(planEventSave({ ...form, title: '定例（臨時）' }, context, 'this')).toEqual({
      kind: 'requests',
      requests: [{
        method: 'POST',
        url: '/calendar/events/7/occurrences/split',
        body: {
          title: '定例（臨時）', location: null, description: null, color_key: 'BLUEBERRY', task_id: null,
          occurrence: { date: '2026-07-14', start_time: '10:00' }, start: '2026-07-14T01:00:00.000Z',
          duration_minutes: 30, expected_version: 4,
        },
      }],
    });
  });

  it('これ以降: この回からの新しい系列（規則を載せる）', () => {
    const { form, context } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    expect(planEventSave(form, context, 'following')).toMatchObject({
      requests: [{
        method: 'POST',
        url: '/calendar/events/7/occurrences/following',
        body: {
          occurrence: { date: '2026-07-14', start_time: '10:00' }, start: '2026-07-14T01:00:00.000Z',
          recurrence: recurringEvent().recurrence, expected_version: 4,
        },
      }],
    });
  });

  it('すべて: 先頭の日（5 月 12 日）はそのまま、時刻だけ入力のものにする', () => {
    const { form, context } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    expect(planEventSave(withStartMinute(form, 660), context, 'all')).toMatchObject({
      requests: [{
        method: 'PUT',
        url: '/calendar/events/7/series',
        body: { start: '2026-05-12T02:00:00.000Z', duration_minutes: 30, recurrence: recurringEvent().recurrence, expected_version: 4 },
      }],
    });
  });

  it('終了日の確かめは、すべてなら系列の先頭・以降ならこの回の日と比べる', () => {
    const { form, context } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    const ended = { ...form, endDate: '2026-06-01' };
    expect(planEventSave(ended, context, 'all').kind).toBe('requests');
    expect(planEventSave(ended, context, 'following')).toEqual({ kind: 'invalid', error: 'endDateBeforeStart' });
  });

  it('繰り返し ↔ 単発（種類を変えた）は、消してから作り直す', () => {
    const { form, context } = formFromEvent(recurringEvent(), recurringOccurrence(), TODAY);
    const plan = planEventSave({ ...form, repeat: 'NONE' }, context, null);
    expect(plan).toMatchObject({
      kind: 'requests',
      requests: [
        { method: 'DELETE', url: '/calendar/events/7', params: { expected_version: 4 } },
        { method: 'POST', url: '/calendar/events', body: { start: '2026-07-14T01:00:00.000Z', recurrence: null, time_zone: TOKYO } },
      ],
    });
  });

  it('振替の回は範囲を聞かずに「この回だけ」として切り出す', () => {
    const moved = recurringOccurrence({ is_moved: true, start: '2026-07-15T05:00:00Z', date: '2026-07-15' });
    const { form, context } = formFromEvent(recurringEvent(), moved, TODAY);
    expect(planEventSave(form, context, null)).toMatchObject({
      requests: [{
        url: '/calendar/events/7/occurrences/split',
        body: { occurrence: { date: '2026-07-14', start_time: '10:00' }, start: '2026-07-15T05:00:00.000Z' },
      }],
    });
  });
});

describe('削除 → API の呼び出し', () => {
  it('単発は予定ごと消す（版は回の event_version）', () => {
    expect(planOccurrenceDelete(apiOccurrence(), null)).toEqual({
      method: 'DELETE', url: '/calendar/events/5', params: { expected_version: 3 },
    });
  });

  it('繰り返しの回は範囲が要る: この回 = 飛ばす・以降 = 前日で終える・すべて = 予定ごと', () => {
    const o = recurringOccurrence();
    expect(planOccurrenceDelete(o, null)).toBeNull();
    expect(planOccurrenceDelete(o, 'this')).toEqual({
      method: 'POST', url: '/calendar/events/7/occurrences/skip',
      body: { occurrence: { date: '2026-07-14', start_time: '10:00' }, expected_version: 4 },
    });
    expect(planOccurrenceDelete(o, 'following')).toMatchObject({ url: '/calendar/events/7/occurrences/delete-following' });
    expect(planOccurrenceDelete(o, 'all')).toEqual({ method: 'DELETE', url: '/calendar/events/7', params: { expected_version: 4 } });
  });
});
