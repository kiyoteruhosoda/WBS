import { useQuery } from '@tanstack/react-query';
import { TRACKER_MOVE_KEY, getTrackerMove } from '../api/trackerMove';
import { hasMovedToTracker } from './trackerMove';

const DEFAULT_TRACKER_URL = 'https://tracker.nolumia.com';

/** 打刻まわりを Tracker へ移したか（task #526 / ADR-0053）。上部の打刻ボタン・「今日」・締め・規則の画面が見る */
export const useTrackerMove = () => {
  const { data } = useQuery({ queryKey: TRACKER_MOVE_KEY, queryFn: getTrackerMove, staleTime: 5 * 60_000 });
  return { moved: hasMovedToTracker(data), url: data?.url ?? DEFAULT_TRACKER_URL };
};
