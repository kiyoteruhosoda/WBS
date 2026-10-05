// 時刻の入力のしかた（task #287、ADR-0039）。⚠ 端末に覚える（localStorage）。サーバには置かない——
// 端末の時刻の欄（<input type="time">）が午前／午後になるかは端末の言語・時計の設定で決まるので、端末ごとの好み。
// 失われても既定（24 時間）に戻るだけ（useProjectScope と同じ判断）。
import { useCallback, useEffect, useState } from 'react';

/** `24h` は自前の欄（数字で打つ・常に 24 時間）、`device` は端末の時刻の欄 */
export type TimeInputStyle = '24h' | 'device';

const KEY = 'wbs.timeInputStyle';
const CHANGED = 'wbs:time-input-style';

const read = (): TimeInputStyle => {
  try {
    return window.localStorage.getItem(KEY) === 'device' ? 'device' : '24h';
  } catch {
    return '24h';
  }
};

export const useTimeInputStyle = (): { style: TimeInputStyle; setStyle: (next: TimeInputStyle) => void } => {
  const [style, setStored] = useState<TimeInputStyle>(read);

  useEffect(() => {
    const sync = () => setStored(read());
    window.addEventListener(CHANGED, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setStyle = useCallback((next: TimeInputStyle) => {
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
