import { describe, expect, it } from 'vitest';
import {
  feedFailureKey, feedFailureOf, importedToOccurrence, withImportedOccurrences,
} from './importedOccurrences';
import type { ImportedOccurrence } from '../types';

const imported: ImportedOccurrence = {
  id: 'imported:7:0',
  calendar_id: 7,
  title: '定例',
  location: '会議室 A',
  start: '2026-10-05T01:00:00Z',
  duration_minutes: 60,
  date: '2026-10-05',
  start_time: '10:00',
  is_all_day: false,
  calendar_color_key: 'GRAPE',
};

describe('importedToOccurrence', () => {
  it('予定の回の形にして、読み取り専用の印を付ける', () => {
    const o = importedToOccurrence(imported, '（件名なし）');
    expect(o).toMatchObject({
      id: 'imported:7:0', event_id: 0, title: '定例', start: imported.start, duration_minutes: 60,
      calendar_id: 7, calendar_color_key: 'GRAPE', color_key: 'DEFAULT', task_id: null, event_type: 'EVENT',
      is_recurring: false, is_done: false, is_imported: true, location: '会議室 A',
    });
  });

  it('件名が空なら代わりの言葉', () => {
    expect(importedToOccurrence({ ...imported, title: '  ' }, '（件名なし）').title).toBe('（件名なし）');
  });

  it('予定の回の後ろに足す（どちらかが無くても描ける）', () => {
    expect(withImportedOccurrences(undefined, [imported], '-')).toHaveLength(1);
    expect(withImportedOccurrences(undefined, undefined, '-')).toEqual([]);
  });
});

describe('feedFailureKey / feedFailureOf', () => {
  it('理由を言葉のキーにする（知らない理由は null）', () => {
    expect(feedFailureKey('not_found')).toBe('calendar.importErrorNotFound');
    expect(feedFailureKey('something_else')).toBeNull();
    expect(feedFailureKey(null)).toBeNull();
  });

  it('422 の応答から理由を取り出す', () => {
    expect(feedFailureOf({ response: { data: { reason: 'forbidden' } } })).toBe('forbidden');
    expect(feedFailureOf({ response: { data: { detail: 'x' } } })).toBeNull();
    expect(feedFailureOf(null)).toBeNull();
  });
});
