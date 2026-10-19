import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { SCHEDULER_MOVE_KEY, getSchedulerMove } from '../api/schedulerMove';
import { errorDetailOf } from '../calendar/calendarRequests';
import { useI18n } from '../i18n';
import { hasMovedToScheduler, schedulerHostOfRefusal } from './schedulerMove';

const DEFAULT_SCHEDULER_URL = 'https://scheduler.nolumia.com';

/** 予定まわりを Scheduler へ移したか（task #535 / ADR-0054）。カレンダー・「今日」・タスク・設定の画面が見る */
export const useSchedulerMove = () => {
  const { data } = useQuery({ queryKey: SCHEDULER_MOVE_KEY, queryFn: getSchedulerMove, staleTime: 5 * 60_000 });
  return { moved: hasMovedToScheduler(data), url: data?.url ?? DEFAULT_SCHEDULER_URL };
};

/**
 * 予定の書き込みが断られた理由（「保存できませんでした。{detail}」の detail）。
 * 「Scheduler に移りました」の 409 なら言葉に直し、移ったことを読み直させる（画面が Scheduler への案内に替わる）。
 */
export const useCalendarFailureDetail = () => {
  const { t } = useI18n();
  const qc = useQueryClient();
  return useCallback((error: unknown): string => {
    const host = schedulerHostOfRefusal(error);
    if (host == null) return errorDetailOf(error) ?? '';
    void qc.invalidateQueries({ queryKey: SCHEDULER_MOVE_KEY });
    return t('scheduler.refused', { host });
  }, [qc, t]);
};
