/**
 * この端末の Web Push の購読（task #193・ADR-0031。形は雛形 fastapitemplate の webPush.ts）。
 *
 * ブラウザの道具（通知の許可・PushManager）は `PushEnvironment` に包み、流れ（許可 → 購読 → サーバへ登録）は
 * ここの関数が持つ。試験は偽の環境で流れを確かめる（webPush.test.ts）。
 *
 * - 購読は Service Worker（sw.js）の登録に付く。⚠ 開発サーバでは Service Worker を登録しないので使えない
 * - 公開鍵が替わったら（サーバの鍵を作り直した）、古い購読を捨てて購読し直す（古い購読には届かない）
 * - 登録し直すのは「この端末で受け取る」を押したときだけ（同じ送り先は 1 件のまま）。別の端末から「外す」を
 *   押した端末へは、その端末で押し直すまで送らない（開いただけで登録し直さない）
 */
import type { PushApi, PushDevice } from '../api/push';

export interface BrowserSubscription {
  endpoint: string;
  /** 購読に使った公開鍵（無い・読めないブラウザもある） */
  applicationServerKey: ArrayBuffer | null;
  toJSON(): { endpoint?: string; keys?: Record<string, string> };
  unsubscribe(): Promise<boolean>;
}

export interface PushEnvironment {
  /** このブラウザ（の今の開き方）で Web Push が使えるか */
  supported: boolean;
  permission(): NotificationPermission;
  requestPermission(): Promise<NotificationPermission>;
  getSubscription(): Promise<BrowserSubscription | null>;
  subscribe(applicationServerKey: Uint8Array<ArrayBuffer>): Promise<BrowserSubscription>;
}

export type ThisDeviceState =
  /** このブラウザは使えない（iPhone はホーム画面に追加して開いたときだけ使える） */
  | 'unsupported'
  /** サーバが送れない設定（鍵が無い） */
  | 'unavailable'
  /** ブラウザで通知が拒否されている */
  | 'denied'
  | 'off'
  | 'on';

/** base64url の公開鍵をバイト列へ */
export const urlBase64ToUint8Array = (value: string): Uint8Array<ArrayBuffer> => {
  const base64 = (value + '='.repeat((4 - (value.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
};

const sameBytes = (a: ArrayBuffer | null, b: Uint8Array): boolean => {
  if (a == null) return true; // 分からないなら同じとみなす（毎回購読し直さない）
  const left = new Uint8Array(a);
  return left.length === b.length && left.every((byte, i) => byte === b[i]);
};

/** 端末の一覧に出す名前（ブラウザ / OS）。秘密は含めない */
export const deviceLabel = (userAgent: string, standalone = false): string => {
  const os = /Android/.test(userAgent) ? 'Android'
    : /iPhone|iPad|iPod/.test(userAgent) ? 'iOS'
      : /Windows/.test(userAgent) ? 'Windows'
        : /Mac OS X|Macintosh/.test(userAgent) ? 'macOS'
          : /CrOS/.test(userAgent) ? 'ChromeOS'
            : /Linux/.test(userAgent) ? 'Linux' : '';
  const browser = /Edg\//.test(userAgent) ? 'Edge'
    : /Firefox\//.test(userAgent) ? 'Firefox'
      : /Chrome\//.test(userAgent) ? 'Chrome'
        : /Safari\//.test(userAgent) ? 'Safari' : 'Browser';
  const name = os ? `${browser} / ${os}` : browser;
  return standalone ? `${name} (PWA)` : name;
};

/** 一覧のうち、この端末の購読（送り先が同じもの） */
export const thisDeviceOf = (devices: PushDevice[], endpoint: string | null): PushDevice | undefined =>
  (endpoint == null ? undefined : devices.find((device) => device.endpoint === endpoint));

const registrationOf = (subscription: BrowserSubscription, label: string) => {
  const json = subscription.toJSON();
  return {
    endpoint: json.endpoint ?? subscription.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
    label,
  };
};

/** この端末の今の状態（許可を求めない・購読しない） */
export const thisDeviceState = async (
  env: PushEnvironment, enabledOnServer: boolean,
): Promise<{ state: ThisDeviceState; endpoint: string | null }> => {
  if (!enabledOnServer) return { state: 'unavailable', endpoint: null };
  if (!env.supported) return { state: 'unsupported', endpoint: null };
  if (env.permission() === 'denied') return { state: 'denied', endpoint: null };
  const subscription = await env.getSubscription();
  if (subscription == null || env.permission() !== 'granted') return { state: 'off', endpoint: null };
  return { state: 'on', endpoint: subscription.endpoint };
};

/** この端末で受け取る（許可を求め、購読し、サーバへ登録する） */
export const enableOnThisDevice = async (
  env: PushEnvironment, api: PushApi, label: string,
): Promise<{ state: ThisDeviceState; device?: PushDevice }> => {
  const config = await api.config();
  if (!config.enabled || config.public_key == null) return { state: 'unavailable' };
  if (!env.supported) return { state: 'unsupported' };
  const current = env.permission();
  const permission = current === 'default' ? await env.requestPermission() : current;
  if (permission !== 'granted') return { state: permission === 'denied' ? 'denied' : 'off' };

  const key = urlBase64ToUint8Array(config.public_key);
  let subscription = await env.getSubscription();
  if (subscription != null && !sameBytes(subscription.applicationServerKey, key)) {
    await subscription.unsubscribe();
    subscription = null;
  }
  subscription ??= await env.subscribe(key);
  const device = await api.register(registrationOf(subscription, label));
  return { state: 'on', device };
};

/** この端末で止める（サーバの登録を外し、ブラウザの購読もやめる） */
export const disableOnThisDevice = async (
  env: PushEnvironment, api: PushApi, devices: PushDevice[],
): Promise<void> => {
  const subscription = env.supported ? await env.getSubscription() : null;
  if (subscription == null) return;
  const device = thisDeviceOf(devices, subscription.endpoint);
  if (device) await api.remove(device.id);
  await subscription.unsubscribe();
};

const wrap = (subscription: PushSubscription): BrowserSubscription => ({
  endpoint: subscription.endpoint,
  applicationServerKey: subscription.options?.applicationServerKey ?? null,
  toJSON: () => subscription.toJSON() as { endpoint?: string; keys?: Record<string, string> },
  unsubscribe: () => subscription.unsubscribe(),
});

/** 本物のブラウザの環境 */
export const browserPushEnvironment = (): PushEnvironment => {
  const supported = typeof window !== 'undefined'
    && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  // ⚠ 開発サーバでは Service Worker を登録しない（ADR-0028）。ready を待つと止まるので、登録の有無で見る
  const registration = async (): Promise<ServiceWorkerRegistration | null> =>
    (supported ? (await navigator.serviceWorker.getRegistration()) ?? null : null);
  return {
    supported,
    permission: () => (supported ? Notification.permission : 'denied'),
    requestPermission: () => Notification.requestPermission(),
    getSubscription: async () => {
      const found = await (await registration())?.pushManager.getSubscription();
      return found ? wrap(found) : null;
    },
    subscribe: async (applicationServerKey) => {
      if ((await registration()) == null) throw new Error('Service Worker is not registered');
      // 登録された直後（まだ有効になっていない）でも購読できるよう、有効になるのを待つ
      const reg = await navigator.serviceWorker.ready;
      return wrap(await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey }));
    },
  };
};

/** この端末の名前（いまの開き方を含める） */
export const thisDeviceLabel = (): string => deviceLabel(
  typeof navigator === 'undefined' ? '' : navigator.userAgent,
  typeof window !== 'undefined' && window.matchMedia?.('(display-mode: standalone)').matches,
);
