// 回を、閲覧者のローカル日ごとの区間に割る（time-model §7）。
//
// ドメインは「開始の瞬間 ＋ 長さ」しか持たない。日をまたぐ回・24 時間を超える回は、閲覧者の
// ローカル 0:00 で割って、続きを翌日の側に描く。割るのは画面だけの仕事。
// 移植元は 2 つまでしか割らなかった（`CalendarViewModel.LoadWeek`）が、こちらは何日でも割る。

import type { CalendarOccurrence } from '../types';
import { MINUTES_PER_DAY, addDays, formatMinute, toZonedPoint } from './zonedTime';

/** ある 1 日の中の、回の 1 区間。 */
export interface DaySegment {
  /** 回の id ＋ 日（区間ごとに一意） */
  key: string;
  occurrence: CalendarOccurrence;
  /** 閲覧者のローカル日 */
  date: string;
  /** その日の 0:00 からの分（0..1440） */
  startMinute: number;
  /** その日の 0:00 からの分（startMinute..1440、排他） */
  endMinute: number;
  isAllDay: boolean;
  /** 前日から続いている */
  continuesFromPreviousDay: boolean;
  /** 翌日へ続く */
  continuesToNextDay: boolean;
}

// 壊れたデータで回り続けないための上限（1 年）。
const MAX_DAYS = 366;

export const occurrenceStartMs = (occurrence: CalendarOccurrence): number => Date.parse(occurrence.start);

export const splitIntoDaySegments = (occurrence: CalendarOccurrence, timeZone: string): DaySegment[] => {
  if (occurrence.is_all_day) {
    return [{
      key: `${occurrence.id}@${occurrence.date}`,
      occurrence,
      date: occurrence.date,
      startMinute: 0,
      endMinute: MINUTES_PER_DAY,
      isAllDay: true,
      continuesFromPreviousDay: false,
      continuesToNextDay: false,
    }];
  }

  const startMs = occurrenceStartMs(occurrence);
  const start = toZonedPoint(startMs, timeZone);
  const duration = Math.max(0, occurrence.duration_minutes);
  if (duration === 0) {
    return [{
      key: `${occurrence.id}@${start.date}`,
      occurrence,
      date: start.date,
      startMinute: start.minute,
      endMinute: start.minute,
      isAllDay: false,
      continuesFromPreviousDay: false,
      continuesToNextDay: false,
    }];
  }

  // 終わりも瞬間から壁時計へ直す（DST をまたいでも、終わりの壁時計は正しい）。
  const end = toZonedPoint(startMs + duration * 60_000, timeZone);
  const segments: DaySegment[] = [];
  let date = start.date;
  for (let i = 0; i < MAX_DAYS; i++) {
    const isFirst = date === start.date;
    const isLast = date === end.date;
    // ちょうど翌 0:00 に終わる回は、翌日に長さ 0 の区間を作らない（その日の下端を 24:00 で閉じる）。
    if (isLast && !isFirst && end.minute === 0) break;
    const startMinute = isFirst ? start.minute : 0;
    const endMinute = isLast ? end.minute : MINUTES_PER_DAY;
    segments.push({
      key: `${occurrence.id}@${date}`,
      occurrence,
      date,
      startMinute,
      endMinute,
      isAllDay: false,
      continuesFromPreviousDay: !isFirst,
      continuesToNextDay: !isLast && !(addDays(date, 1) === end.date && end.minute === 0),
    });
    if (isLast) break;
    date = addDays(date, 1);
  }
  return segments;
};

/** 回の並び: 終日が先、あとは開始の早い順（移植元の月表示の並べ方）。 */
export const compareSegments = (a: DaySegment, b: DaySegment): number => {
  if (a.isAllDay !== b.isAllDay) return a.isAllDay ? -1 : 1;
  if (a.startMinute !== b.startMinute) return a.startMinute - b.startMinute;
  if (a.endMinute !== b.endMinute) return b.endMinute - a.endMinute;
  return a.occurrence.id < b.occurrence.id ? -1 : a.occurrence.id > b.occurrence.id ? 1 : 0;
};

/** 回をすべて割り、日ごとに束ねる（各日の中は `compareSegments` の順）。 */
export const groupSegmentsByDate = (
  occurrences: readonly CalendarOccurrence[],
  timeZone: string,
): Map<string, DaySegment[]> => {
  const byDate = new Map<string, DaySegment[]>();
  for (const occurrence of occurrences) {
    for (const segment of splitIntoDaySegments(occurrence, timeZone)) {
      const list = byDate.get(segment.date);
      if (list) list.push(segment);
      else byDate.set(segment.date, [segment]);
    }
  }
  for (const list of byDate.values()) list.sort(compareSegments);
  return byDate;
};

/**
 * 回の時刻の表示（`09:00 – 10:30`）。終わりがちょうど翌 0:00 なら `24:00`、
 * それより先へまたぐ回は終わりの壁時計（移植元の `CalendarEventItem.TimeRange`）。
 * 終日は null（呼び手が「終日」と書く）。
 */
export const formatOccurrenceTimeRange = (occurrence: CalendarOccurrence, timeZone: string): string | null => {
  if (occurrence.is_all_day) return null;
  const startMs = occurrenceStartMs(occurrence);
  const start = toZonedPoint(startMs, timeZone);
  const end = toZonedPoint(startMs + Math.max(0, occurrence.duration_minutes) * 60_000, timeZone);
  const endsAtNextMidnight = end.minute === 0 && end.date === addDays(start.date, 1);
  return `${formatMinute(start.minute)} – ${endsAtNextMidnight ? '24:00' : formatMinute(end.minute)}`;
};

/** 区間の時刻の表示（その日の中だけ。下端が 0:00 の翌日なら 24:00）。 */
export const formatSegmentTimeRange = (segment: DaySegment): string =>
  `${formatMinute(segment.startMinute)} – ${formatMinute(segment.endMinute)}`;
