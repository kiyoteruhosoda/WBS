// 時刻の表記（12 時間／24 時間。task #287、ADR-0039）。⚠ 端末に覚える（localStorage）。サーバには置かない——
// 端末ごとの好みで、失われても既定（24 時間）に戻るだけ（useProjectScope と同じ判断）。
import { useCallback, useEffect, useState } from 'react';
import type { ClockStyle } from '../clock/clockFace';

const KEY = 'wbs.clockStyle';
const CHANGED = 'wbs:clock-style';

const read = (): ClockStyle => {
  try {
    return window.localStorage.getItem(KEY) === '12h' ? '12h' : '24h';
  } catch {
    return '24h';
  }
};

export const useClockStyle = (): { style: ClockStyle; setStyle: (next: ClockStyle) => void } => {
  const [style, setStored] = useState<ClockStyle>(read);

  useEffect(() => {
    const sync = () => setStored(read());
    window.addEventListener(CHANGED, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setStyle = useCallback((next: ClockStyle) => {
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // 覚えられないだけで、画面は動く
    }
    setStored(next);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  return { style, setStyle };
};
