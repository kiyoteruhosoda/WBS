// 予定の通知の音の入り切り（task #520、ADR-0052）。⚠ 端末に覚える（localStorage）。サーバには置かない——
// 端末ごとの好みで、失われても既定（鳴らす）に戻るだけ（inPageAlarm.ts と同じ判断）。
// 端末への通知（Web Push）は Service Worker が出し、Service Worker は localStorage を読めないので、Cache Storage にも写す。
import { useCallback, useEffect, useState } from 'react';

const KEY = 'wbs.alarmSound';
const CHANGED = 'wbs:alarm-sound';
/** ⚠ serviceWorker/pushNotice.ts と同じ値（束を分けるため import しない。pushNotice.test.ts で揃いを守る） */
export const ALARM_SOUND_CACHE = 'wbs-prefs';
export const ALARM_SOUND_KEY = '/__prefs/alarm-sound';
export const ALARM_SOUND_OFF = 'off';

const read = (): boolean => {
  try {
    return window.localStorage.getItem(KEY) !== ALARM_SOUND_OFF;
  } catch {
    return true;
  }
};

/** Service Worker が読む写しを書く。Cache Storage が無い・使えないブラウザでは、端末への通知は端末の設定どおり鳴る */
const mirror = (sound: boolean): void => {
  if (typeof caches === 'undefined') return;
  void caches.open(ALARM_SOUND_CACHE)
    .then((cache) => cache.put(ALARM_SOUND_KEY, new Response(sound ? 'on' : ALARM_SOUND_OFF)))
    .catch(() => undefined);
};

/** `sound` が true なら鳴らす（既定）、false なら予定の通知を音なしで出す */
export const useAlarmSoundSetting = (): { sound: boolean; setSound: (next: boolean) => void } => {
  const [sound, setStored] = useState<boolean>(read);

  // 写しは今の値に合わせ続ける（Cache Storage だけ消された・前の版で写していなかった端末でも揃う）
  useEffect(() => {
    mirror(sound);
  }, [sound]);

  useEffect(() => {
    const sync = () => setStored(read());
    window.addEventListener(CHANGED, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setSound = useCallback((next: boolean) => {
    try {
      window.localStorage.setItem(KEY, next ? 'on' : ALARM_SOUND_OFF);
    } catch {
      // 覚えられないだけで、画面は動く
    }
    setStored(next);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

  return { sound, setSound };
};
