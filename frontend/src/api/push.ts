// 端末への通知（Web Push）の設定の口（task #193・ADR-0031）。
import client from './client';

export interface PushConfig {
  /** この配備が端末への通知を送れるか（鍵が無ければ false） */
  enabled: boolean;
  /** ブラウザの購読に渡す公開鍵（base64url） */
  public_key: string | null;
}

export interface PushPreferences {
  event_alarm: boolean;
  routine_start: boolean;
  timer_left_running: boolean;
  closing_due: boolean;
  timer_left_running_hours: number;
}

export interface PushDevice {
  id: number;
  endpoint: string;
  label: string;
  /** 予定から出る通知（予定の通知・定常業務の開始）をこの端末へ送るか */
  receives_calendar: boolean;
  created_at: string | null;
  last_sent_at: string | null;
}

export interface PushDeviceRegistration {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  label: string;
}

export const getPushConfig = async (): Promise<PushConfig> => (await client.get('/push/config')).data;

export const getPushPreferences = async (): Promise<PushPreferences> =>
  (await client.get('/push/preferences')).data;

export const updatePushPreferences = async (patch: Partial<PushPreferences>): Promise<PushPreferences> =>
  (await client.put('/push/preferences', patch)).data;

export const listPushDevices = async (): Promise<PushDevice[]> => (await client.get('/push/subscriptions')).data;

export const registerPushDevice = async (body: PushDeviceRegistration): Promise<PushDevice> =>
  (await client.post('/push/subscriptions', body)).data;

export const setDeviceReceivesCalendar = async (id: number, receivesCalendar: boolean): Promise<PushDevice> =>
  (await client.patch(`/push/subscriptions/${id}`, { receives_calendar: receivesCalendar })).data;

export const removePushDevice = async (id: number): Promise<void> => {
  await client.delete(`/push/subscriptions/${id}`);
};

export const pushApi = {
  config: getPushConfig,
  register: registerPushDevice,
  remove: removePushDevice,
};

export type PushApi = typeof pushApi;
