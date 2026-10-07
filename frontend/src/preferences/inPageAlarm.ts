// 「画面の中で知らせる」の入り切り（task #312、ADR-0041）。⚠ 端末に覚える（localStorage）。サーバには置かない——
// 端末ごとの好みで、失われても既定（入）に戻るだけ（clockStyle と同じ判断）。
import { useCallback, useEffect, useState } from 'react';

const KEY = 'wbs.inPageAlarm';
const CHANGED = 'wbs:in-page-alarm';

const read = (): boolean => {
  try {
    return window.localStorage.getItem(KEY) !== 'off';
  } catch {
    return true;
  }
};

export const useInPageAlarmSetting = (): { enabled: boolean; setEnabled: (next: boolean) => void } => {
  const [enabled, setStored] = useState<boolean>(read);

  useEffect(() => {
    const sync = () => setStored(read());
    window.addEventListener(CHANGED, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setEnabled = useCallback((next: boolean) => {
    try {
      window.localStorage.setItem(KEY, next ? 'on' : 'off');
    } catch {
      // 覚えられないだけで、画面は動く
    }
    setStored(next);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  return { enabled, setEnabled };
};
