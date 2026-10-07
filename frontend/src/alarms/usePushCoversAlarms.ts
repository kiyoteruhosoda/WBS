// この端末で Web Push の予定の通知を受け取っているか（task #312、ADR-0041）。
import { useQuery } from '@tanstack/react-query';
import { getPushConfig, getPushPreferences, listPushDevices } from '../api/push';
import { browserPushEnvironment, thisDeviceState } from '../pwa/webPush';
import { pushCoversAlarms } from './inPageAlarm';

/**
 * この端末で Web Push の予定の通知を受け取っているか。設定画面（PushSettings）と同じ問い合わせの鍵を使い、
 * 設定を変えるとこちらも引き直す。分からない間・取れないときは「受け取っていない」（画面の中で鳴らす）。
 */
export const usePushCoversAlarms = (): boolean => {
  const config = useQuery({ queryKey: ['push', 'config'], queryFn: getPushConfig });
  const serverEnabled = config.data?.enabled ?? false;
  const preferences = useQuery({ queryKey: ['push', 'preferences'], queryFn: getPushPreferences, enabled: serverEnabled });
  const devices = useQuery({ queryKey: ['push', 'devices'], queryFn: listPushDevices, enabled: serverEnabled });
  const thisDevice = useQuery({
    queryKey: ['push', 'thisDevice'],
    queryFn: async () => (await thisDeviceState(browserPushEnvironment(), true)).endpoint,
    enabled: serverEnabled,
  });
  return pushCoversAlarms({
    serverEnabled,
    endpoint: thisDevice.data ?? null,
    devices: devices.data ?? [],
    eventAlarm: preferences.data?.event_alarm ?? false,
  });
};
