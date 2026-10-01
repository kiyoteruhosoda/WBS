import { describe, expect, it } from 'vitest';
import { TODAY_SUMMARY_KEY } from '../api/today';
import { OCCURRENCES_QUERY, queriesAfterEventWrite } from './calendarQueries';

describe('予定を書いたあとに読み直させるもの（task #185）', () => {
  it('回と、「今日」の画面の要約・タスクの予定済みの時間を含む', () => {
    const keys = queriesAfterEventWrite();
    expect(keys).toContainEqual([OCCURRENCES_QUERY]);
    expect(keys).toContainEqual(TODAY_SUMMARY_KEY);
    expect(keys).toContainEqual(['tasks']);
  });

  it('「今日」の画面の回のキー（1 日だけの期間）にも前方一致で当たる', () => {
    const todayKey = [OCCURRENCES_QUERY, '2026-10-01', '2026-10-01', 'Asia/Tokyo'];
    expect(queriesAfterEventWrite().some((k) => k.every((part, i) => todayKey[i] === part))).toBe(true);
  });
});
