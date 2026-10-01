// 予定の編集画面の中身と、保存・削除の呼び出しへの変換（移植元 `EventEditViewModel`、ADR-0010）。
//
// 画面の入力は予定のタイムゾーンの壁時計（日 ＋ 分）で持ち、API へ渡すときに UTC の瞬間 ＋ 長さへ
// 直す（time-model §4）。新しい予定は閲覧者のタイムゾーン（利用者設定）で作る。

import type {
  AdjustmentRuleData, CalendarEvent, CalendarOccurrence, EventColorKey, MonthlyRuleData, RecurrenceRuleData,
  WeekdayCode, YearlyRuleData,
} from '../types';
import type { CalendarRequest } from './calendarRequests';
import { deleteEventRequest, occurrenceActionRequest, occurrenceKeyOf } from './calendarRequests';
import {
  MINUTES_PER_DAY, addDays, dayOfMonth, dayOfWeek, fromZonedPoint, toZonedPoint, yearMonthOf,
} from './zonedTime';

export type RepeatType = 'NONE' | 'WEEKLY' | 'MONTHLY' | 'YEARLY';
/** 繰り返しの予定を直す・消す範囲（移植元 `RecurringEditScope`）。 */
export type RecurringScope = 'this' | 'following' | 'all';
/** 営業日シフトの日付タイプ: 予定日（祝日のときだけ寄せる）・基準日（常に N 営業日寄せる）。 */
export type AdjustmentDateType = 'SCHEDULED' | 'BASE';
export type AdjustmentDirection = 'BEFORE' | 'AFTER' | 'CANCEL';

/** 0 = 日曜 … 6 = 土曜 の並び（移植元 `WeekdayItems`）。 */
export const WEEKDAY_CODES: readonly WeekdayCode[] = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
/** 第 n の選び方（-1 は最終）。 */
export const WEEK_INDEXES: readonly number[] = [1, 2, 3, 4, 5, -1];
export const EVENT_COLOR_KEYS: readonly EventColorKey[] = [
  'DEFAULT', 'TOMATO', 'TANGERINE', 'BANANA', 'BASIL', 'SAGE', 'PEACOCK', 'BLUEBERRY', 'LAVENDER', 'GRAPE', 'GRAPHITE',
];

/** 新しい予定の既定の長さと最短（移植元 `EventEditDefaults`）。 */
export const DEFAULT_DURATION_MINUTES = 30;
export const MIN_DURATION_MINUTES = 15;
const TIME_STEP_MINUTES = 15;
const DEFAULT_START_MINUTE = 9 * 60;

export interface EventForm {
  title: string;
  location: string;
  memo: string;
  /** 入力の壁時計のタイムゾーン（既存の予定は予定のもの、新しい予定は閲覧者のもの） */
  timeZone: string;
  allDay: boolean;
  startDate: string;
  /** 開始（その日の 0:00 からの分） */
  startMinute: number;
  /** 長さ（分）。終了の入力はここから出し、ここへ戻す（開始を動かすと終了も同じだけ動く） */
  durationMinutes: number;
  repeat: RepeatType;
  useCustomInterval: boolean;
  interval: number;
  hasEndDate: boolean;
  endDate: string;
  weekdays: WeekdayCode[];
  monthlyKind: 'DAY_OF_MONTH' | 'NTH_WEEKDAY';
  /** 「月末」（毎月○日の横のチェック） */
  monthlyLastDay: boolean;
  dayOfMonth: number;
  monthlyWeekIndex: number;
  monthlyWeekday: WeekdayCode;
  yearlyKind: 'DAY_OF_MONTH' | 'NTH_WEEKDAY';
  yearlyMonth: number;
  yearlyDay: number;
  yearlyWeekIndex: number;
  yearlyWeekday: WeekdayCode;
  useAdjustment: boolean;
  adjustmentDateType: AdjustmentDateType;
  adjustmentDirection: AdjustmentDirection;
  adjustmentDays: number;
  adjustmentCalendarId: number | null;
  colorKey: EventColorKey;
  taskId: number | null;
}

/** 何を開いているか。保存の呼び出しの選び方が変わる。 */
export type EventFormContext =
  | { mode: 'create' }
  | {
    mode: 'edit';
    event: CalendarEvent;
    /** 回から開いたとき（繰り返しの範囲を聞く・回の鍵を使う） */
    occurrence: CalendarOccurrence | null;
    /** 振替（この回だけ動かした回）。単発として扱い、範囲は聞かない（移植元 `_isMovedOccurrence`） */
    isMovedOccurrence: boolean;
  };

// ── 時刻の候補 ────────────────────────────────────────────────────────────

const timeSteps = (from: number, to: number): number[] => {
  const list: number[] = [];
  for (let m = from; m <= to; m += TIME_STEP_MINUTES) list.push(m);
  return list;
};

const withOffGrid = (list: number[], current: number): number[] =>
  list.includes(current) ? list : [...list, current].sort((a, b) => a - b);

/** 開始の候補（15 分おき 00:00〜23:45。今の値が刻みから外れていれば差し込む）。 */
export const startTimeOptions = (current: number): number[] => withOffGrid(timeSteps(0, MINUTES_PER_DAY - TIME_STEP_MINUTES), current);

/** 終了の候補（15 分おき 00:00〜23:45 の末尾に 24:00）。 */
export const endTimeOptions = (current: number): number[] => withOffGrid(timeSteps(0, MINUTES_PER_DAY), current);

/** `HH:MM`（`24:00` を含む）→ 分。読めなければ null。 */
export const parseTime = (text: string): number | null => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!m) return null;
  const minute = Number(m[1]) * 60 + Number(m[2]);
  if (Number(m[2]) >= 60 || minute > MINUTES_PER_DAY) return null;
  return minute;
};

/** 終了の壁時計（その日の分 1..1440 と、開始日から何日後か）。 */
export const endOf = (form: Pick<EventForm, 'startMinute' | 'durationMinutes'>): { minute: number; dayOffset: number } => {
  const absolute = form.startMinute + Math.max(0, form.durationMinutes);
  if (absolute > 0 && absolute % MINUTES_PER_DAY === 0) return { minute: MINUTES_PER_DAY, dayOffset: absolute / MINUTES_PER_DAY - 1 };
  return { minute: absolute % MINUTES_PER_DAY, dayOffset: Math.floor(absolute / MINUTES_PER_DAY) };
};

/** 開始を変える。長さはそのまま（終了も同じだけ動く。移植元 `SetStartTimePreservingDuration`）。 */
export const withStartMinute = (form: EventForm, startMinute: number): EventForm => ({ ...form, startMinute });

/** 終了を変える。開始以前を選んだら翌日のその時刻（日をまたぐ予定）。 */
export const withEndMinute = (form: EventForm, endMinute: number): EventForm => {
  const duration = endMinute > form.startMinute ? endMinute - form.startMinute : endMinute + MINUTES_PER_DAY - form.startMinute;
  return { ...form, durationMinutes: Math.max(MIN_DURATION_MINUTES, duration) };
};

// ── 作る・読み込む ────────────────────────────────────────────────────────

const weekIndexOfDate = (date: string): number => Math.min(5, Math.floor((dayOfMonth(date) - 1) / 7) + 1);

/** 繰り返しの選び方を開始日に合わせる（移植元 `ApplyStartDateRecurrenceDefaults`）。 */
export const withStartDateRecurrenceDefaults = (form: EventForm): EventForm => {
  const weekday = WEEKDAY_CODES[dayOfWeek(form.startDate)];
  const weekIndex = weekIndexOfDate(form.startDate);
  const { month } = yearMonthOf(form.startDate);
  return {
    ...form,
    weekdays: [weekday],
    dayOfMonth: dayOfMonth(form.startDate),
    monthlyWeekday: weekday,
    monthlyWeekIndex: weekIndex,
    yearlyMonth: month,
    yearlyDay: dayOfMonth(form.startDate),
    yearlyWeekday: weekday,
    yearlyWeekIndex: weekIndex,
  };
};

/** 繰り返しの種類を変える。なしから選んだときだけ、曜日・日・月を開始日に合わせる。 */
export const withRepeat = (form: EventForm, repeat: RepeatType): EventForm => {
  const next = { ...form, repeat };
  return form.repeat === 'NONE' && repeat !== 'NONE' ? withStartDateRecurrenceDefaults(next) : next;
};

const snapToStep = (minute: number): number =>
  Math.min(MINUTES_PER_DAY - TIME_STEP_MINUTES, Math.max(0, Math.round(minute / TIME_STEP_MINUTES) * TIME_STEP_MINUTES));

/**
 * 新しい予定の中身（移植元 `InitializeNewEvent`）。開始は 15 分に丸め、終了を渡されなければ 30 分。
 * 終了は開始より 15 分以上後、その日の 24:00 まで。
 */
export const newEventForm = (
  { date, startMinute, endMinute, timeZone, today, calendarIds = [] }: {
    date: string;
    startMinute?: number;
    endMinute?: number;
    timeZone: string;
    today: string;
    /** 営業日カレンダーが 1 つだけなら、それを最初から選んでおく */
    calendarIds?: readonly number[];
  },
): EventForm => {
  const start = snapToStep(startMinute ?? DEFAULT_START_MINUTE);
  const end = endMinute == null
    ? Math.min(start + DEFAULT_DURATION_MINUTES, MINUTES_PER_DAY)
    : Math.min(Math.max(endMinute, start + MIN_DURATION_MINUTES), MINUTES_PER_DAY);
  return withStartDateRecurrenceDefaults({
    title: '',
    location: '',
    memo: '',
    timeZone,
    allDay: false,
    startDate: date,
    startMinute: start,
    durationMinutes: end - start,
    repeat: 'NONE',
    useCustomInterval: false,
    interval: 1,
    hasEndDate: false,
    endDate: addDays(today, 365),
    weekdays: ['MO'],
    monthlyKind: 'DAY_OF_MONTH',
    monthlyLastDay: false,
    dayOfMonth: 1,
    monthlyWeekIndex: 1,
    monthlyWeekday: 'SU',
    yearlyKind: 'DAY_OF_MONTH',
    yearlyMonth: 1,
    yearlyDay: 1,
    yearlyWeekIndex: 1,
    yearlyWeekday: 'SU',
    useAdjustment: false,
    adjustmentDateType: 'SCHEDULED',
    adjustmentDirection: 'BEFORE',
    adjustmentDays: 1,
    adjustmentCalendarId: calendarIds.length === 1 ? calendarIds[0] : null,
    colorKey: 'DEFAULT',
    taskId: null,
  });
};

/** 保存してある規則を入力へ（移植元 `LoadRecurrenceRuleCore`）。 */
const withRecurrenceRule = (form: EventForm, rule: RecurrenceRuleData): EventForm => {
  const next: EventForm = {
    ...form,
    repeat: rule.type,
    hasEndDate: rule.end_date != null,
    endDate: rule.end_date ?? form.endDate,
    useCustomInterval: rule.interval > 1,
    interval: rule.interval,
  };
  if (rule.type === 'WEEKLY' && rule.weekly) {
    next.weekdays = WEEKDAY_CODES.filter((w) => rule.weekly?.weekdays.includes(w));
  }
  if (rule.type === 'MONTHLY' && rule.monthly) {
    const m = rule.monthly;
    if (m.kind === 'NTH_WEEKDAY') {
      next.monthlyKind = 'NTH_WEEKDAY';
      next.monthlyWeekIndex = m.week_index ?? 1;
      next.monthlyWeekday = m.weekday ?? next.monthlyWeekday;
    } else {
      next.monthlyKind = 'DAY_OF_MONTH';
      next.monthlyLastDay = m.kind === 'LAST_DAY';
      if (m.kind === 'DAY_OF_MONTH') next.dayOfMonth = m.day ?? next.dayOfMonth;
    }
  }
  if (rule.type === 'YEARLY' && rule.yearly) {
    const y = rule.yearly;
    next.yearlyKind = y.kind;
    next.yearlyMonth = y.month;
    if (y.kind === 'DAY_OF_MONTH') next.yearlyDay = y.day ?? next.yearlyDay;
    else {
      next.yearlyWeekIndex = y.week_index ?? 1;
      next.yearlyWeekday = y.weekday ?? next.yearlyWeekday;
    }
  }
  const a = rule.adjustment;
  if (a) {
    next.useAdjustment = true;
    next.adjustmentDateType = a.condition === 'HOLIDAY' ? 'SCHEDULED' : 'BASE';
    next.adjustmentDirection = a.action === 'CANCEL' ? 'CANCEL' : a.shift_amount < 0 ? 'BEFORE' : 'AFTER';
    next.adjustmentDays = a.action === 'CANCEL' ? 1 : Math.abs(a.shift_amount);
    next.adjustmentCalendarId = a.calendar_id;
  }
  return next;
};

/**
 * 既存の予定を入力へ（移植元 `LoadEvent`）。回から開いたら、その回の位置（予定のタイムゾーン）を
 * 開始に出す。振替の回は単発として見せる（繰り返しの欄は「なし」）。
 */
export const formFromEvent = (
  event: CalendarEvent,
  occurrence: CalendarOccurrence | null,
  today: string,
): { form: EventForm; context: EventFormContext } => {
  const timeZone = event.time_zone;
  const startMs = Date.parse(occurrence?.start ?? event.start);
  const duration = occurrence?.duration_minutes ?? event.duration_minutes;
  const point = toZonedPoint(startMs, timeZone);
  const allDay = occurrence ? occurrence.is_all_day : point.minute === 0 && duration === MINUTES_PER_DAY;
  const startDate = allDay && occurrence ? occurrence.date : point.date;
  const isMovedOccurrence = occurrence != null && event.kind === 'RECURRING' && occurrence.is_moved;

  let form: EventForm = {
    ...newEventForm({ date: startDate, timeZone, today }),
    title: event.title,
    location: event.location ?? '',
    memo: event.description ?? '',
    allDay,
    startMinute: allDay ? DEFAULT_START_MINUTE : point.minute,
    durationMinutes: allDay ? DEFAULT_DURATION_MINUTES : Math.max(MIN_DURATION_MINUTES, duration),
    colorKey: event.color_key,
    taskId: event.task_id,
  };
  if (event.recurrence && !isMovedOccurrence) form = withRecurrenceRule(form, event.recurrence);
  return { form, context: { mode: 'edit', event, occurrence, isMovedOccurrence } };
};

// ── 入力 → API の形 ───────────────────────────────────────────────────────

/** 営業日シフト（移植元 `BuildAdjustmentRule`）。使わない・0 日なら null。 */
export const buildAdjustment = (form: EventForm): AdjustmentRuleData | null => {
  if (!form.useAdjustment) return null;
  const condition = form.adjustmentDateType === 'SCHEDULED' ? 'HOLIDAY' : 'ALWAYS';
  if (condition === 'HOLIDAY' && form.adjustmentDirection === 'CANCEL') {
    return { condition, shift_unit: 'BUSINESS_DAY', shift_amount: 0, calendar_id: form.adjustmentCalendarId, action: 'CANCEL' };
  }
  if (form.adjustmentDays <= 0) return null;
  // 基準日は「前・後」だけ（キャンセルは予定日のときだけ選べる）。
  const amount = form.adjustmentDirection === 'AFTER' ? form.adjustmentDays : -form.adjustmentDays;
  return { condition, shift_unit: 'BUSINESS_DAY', shift_amount: amount, calendar_id: form.adjustmentCalendarId, action: 'SHIFT' };
};

/** 繰り返しの規則（移植元 `BuildRecurrenceRule`）。繰り返さないなら null。 */
export const buildRecurrence = (form: EventForm): RecurrenceRuleData | null => {
  if (form.repeat === 'NONE') return null;
  const base = {
    interval: form.useCustomInterval ? Math.max(1, form.interval) : 1,
    end_date: form.hasEndDate ? form.endDate : null,
    weekly: null,
    monthly: null,
    yearly: null,
    adjustment: buildAdjustment(form),
  };
  if (form.repeat === 'WEEKLY') {
    return { ...base, type: 'WEEKLY', weekly: { weekdays: WEEKDAY_CODES.filter((w) => form.weekdays.includes(w)) } };
  }
  if (form.repeat === 'MONTHLY') {
    let monthly: MonthlyRuleData;
    if (form.monthlyKind === 'NTH_WEEKDAY') {
      monthly = { kind: 'NTH_WEEKDAY', week_index: form.monthlyWeekIndex, weekday: form.monthlyWeekday };
    } else if (form.monthlyLastDay) {
      monthly = { kind: 'LAST_DAY' };
    } else {
      monthly = { kind: 'DAY_OF_MONTH', day: form.dayOfMonth };
    }
    return { ...base, type: 'MONTHLY', monthly };
  }
  const yearly: YearlyRuleData = form.yearlyKind === 'NTH_WEEKDAY'
    ? { kind: 'NTH_WEEKDAY', month: form.yearlyMonth, week_index: form.yearlyWeekIndex, weekday: form.yearlyWeekday }
    : { kind: 'DAY_OF_MONTH', month: form.yearlyMonth, day: form.yearlyDay };
  return { ...base, type: 'YEARLY', yearly };
};

/** その日の開始の UTC 瞬間（Z 付き ISO 8601、分の単位）。終日は 0:00。 */
export const startInstantOf = (form: EventForm, date = form.startDate): string =>
  new Date(fromZonedPoint(date, form.allDay ? 0 : form.startMinute, form.timeZone)).toISOString();

export const durationOf = (form: EventForm): number => (form.allDay ? MINUTES_PER_DAY : form.durationMinutes);

const textOrNull = (text: string): string | null => (text.trim() === '' ? null : text.trim());

const details = (form: EventForm) => ({
  title: form.title.trim(),
  location: textOrNull(form.location),
  description: textOrNull(form.memo),
  color_key: form.colorKey,
  task_id: form.taskId,
});

// ── 保存・削除の段取り ────────────────────────────────────────────────────

export type FormError = 'titleRequired' | 'weekdayRequired' | 'endDateBeforeStart';

export type SavePlan =
  | { kind: 'requests'; requests: CalendarRequest[] }
  | { kind: 'needsScope' }
  | { kind: 'invalid'; error: FormError };

const isRecurringForm = (form: EventForm): boolean => form.repeat !== 'NONE';

/** 繰り返しの予定の回から開いたか（範囲を聞くか）。移植元 `RequiresRecurringEditScopeSelection`。 */
export const needsRecurringScope = (form: EventForm, context: EventFormContext): boolean =>
  context.mode === 'edit' && context.event.kind === 'RECURRING' && !context.isMovedOccurrence
  && isRecurringForm(form) && context.occurrence != null;

const seriesStartDate = (event: CalendarEvent): string => toZonedPoint(Date.parse(event.start), event.time_zone).date;

const validate = (form: EventForm, seriesStart: string | null): FormError | null => {
  if (form.title.trim() === '') return 'titleRequired';
  if (!isRecurringForm(form)) return null;
  if (form.repeat === 'WEEKLY' && form.weekdays.length === 0) return 'weekdayRequired';
  if (form.hasEndDate && form.endDate < (seriesStart ?? form.startDate)) return 'endDateBeforeStart';
  return null;
};

const createRequest = (form: EventForm): CalendarRequest => ({
  method: 'POST',
  url: '/calendar/events',
  body: {
    ...details(form),
    time_zone: form.timeZone,
    start: startInstantOf(form),
    duration_minutes: durationOf(form),
    recurrence: buildRecurrence(form),
  },
});

/**
 * 保存の呼び出し（移植元 `EventEditViewModel.Save`）。繰り返しの回から開いて範囲がまだなら `needsScope`。
 *
 * - 新しい予定: 作る（繰り返しがあれば繰り返し）
 * - 振替の回: 「この回だけ」として単発に切り出す
 * - 単発 ↔ 繰り返し（種類を変えた）: 消して作り直す
 * - 繰り返しの回: この回だけ（切り出し）・以降（新しい系列）・すべて（系列を置き換え。先頭の日はそのまま）
 * - 単発: 詳細と日時を置き換える
 */
export const planEventSave = (form: EventForm, context: EventFormContext, scope: RecurringScope | null): SavePlan => {
  if (context.mode === 'create') {
    const error = validate(form, null);
    return error ? { kind: 'invalid', error } : { kind: 'requests', requests: [createRequest(form)] };
  }
  const { event, occurrence } = context;
  const version = event.version;
  const wasRecurring = event.kind === 'RECURRING';

  if (context.isMovedOccurrence && occurrence) {
    const error = validate({ ...form, repeat: 'NONE' }, null);
    if (error) return { kind: 'invalid', error };
    return {
      kind: 'requests',
      requests: [{
        method: 'POST',
        url: `/calendar/events/${event.id}/occurrences/split`,
        body: {
          ...details(form), occurrence: occurrenceKeyOf(occurrence), start: startInstantOf(form),
          duration_minutes: durationOf(form), expected_version: version,
        },
      }],
    };
  }

  if (wasRecurring !== isRecurringForm(form)) {
    const error = validate(form, null);
    if (error) return { kind: 'invalid', error };
    return { kind: 'requests', requests: [deleteEventRequest(event.id, version), createRequest(form)] };
  }

  if (wasRecurring) {
    if (needsRecurringScope(form, context) && scope == null) return { kind: 'needsScope' };
    const effectiveScope: RecurringScope = occurrence && !context.isMovedOccurrence ? scope ?? 'all' : 'all';
    if (effectiveScope === 'this' && occurrence) {
      const error = validate({ ...form, repeat: 'NONE' }, null);
      if (error) return { kind: 'invalid', error };
      return {
        kind: 'requests',
        requests: [{
          method: 'POST',
          url: `/calendar/events/${event.id}/occurrences/split`,
          body: {
            ...details(form), occurrence: occurrenceKeyOf(occurrence), start: startInstantOf(form),
            duration_minutes: durationOf(form), expected_version: version,
          },
        }],
      };
    }
    if (effectiveScope === 'following' && occurrence) {
      const error = validate(form, null);
      if (error) return { kind: 'invalid', error };
      return {
        kind: 'requests',
        requests: [{
          method: 'POST',
          url: `/calendar/events/${event.id}/occurrences/following`,
          body: {
            ...details(form), occurrence: occurrenceKeyOf(occurrence), start: startInstantOf(form),
            duration_minutes: durationOf(form), recurrence: buildRecurrence(form), expected_version: version,
          },
        }],
      };
    }
    // すべて: 先頭の日はそのまま（振替・飛ばしの鍵が同じ候補日に付いたまま残る）。時刻だけ入力のもの。
    const anchorDate = seriesStartDate(event);
    const error = validate(form, anchorDate);
    if (error) return { kind: 'invalid', error };
    return {
      kind: 'requests',
      requests: [{
        method: 'PUT',
        url: `/calendar/events/${event.id}/series`,
        body: {
          ...details(form), start: startInstantOf(form, anchorDate), duration_minutes: durationOf(form),
          recurrence: buildRecurrence(form), expected_version: version,
        },
      }],
    };
  }

  const error = validate(form, null);
  if (error) return { kind: 'invalid', error };
  return {
    kind: 'requests',
    requests: [{
      method: 'PUT',
      url: `/calendar/events/${event.id}`,
      body: { ...details(form), start: startInstantOf(form), duration_minutes: durationOf(form), expected_version: version },
    }],
  };
};

/**
 * 削除の呼び出し（移植元 `DeleteOccurrence` / `DeleteOccurrenceAndFollowing` / `DeleteEntireEvent`）。
 * 繰り返しの回は範囲が要る（この回 = 飛ばす・以降 = 前日で終える・すべて = 予定ごと）。
 */
export const planOccurrenceDelete = (
  occurrence: CalendarOccurrence,
  scope: RecurringScope | null,
): CalendarRequest | null => {
  const version = occurrence.event_version;
  if (!occurrence.is_recurring || !occurrence.series_key) return deleteEventRequest(occurrence.event_id, version);
  if (scope == null) return null;
  if (scope === 'this') return occurrenceActionRequest(occurrence.event_id, 'skip', occurrenceKeyOf(occurrence), version);
  if (scope === 'following') return occurrenceActionRequest(occurrence.event_id, 'delete-following', occurrenceKeyOf(occurrence), version);
  return deleteEventRequest(occurrence.event_id, version);
};
