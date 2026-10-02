import { describe, expect, it } from 'vitest';
import type { PushApi, PushConfig, PushDevice, PushDeviceRegistration } from '../api/push';
import {
  deviceLabel, disableOnThisDevice, enableOnThisDevice, thisDeviceOf, thisDeviceState,
  urlBase64ToUint8Array,
} from './webPush';
import type { BrowserSubscription, PushEnvironment } from './webPush';

const KEY = 'BAEC'; // 0x04 0x01 0x02
const OTHER_KEY = 'BAMD';

const bytes = (key: string): ArrayBuffer => urlBase64ToUint8Array(key).buffer;

class FakeSubscription implements BrowserSubscription {
  unsubscribed = false;
  endpoint: string;
  applicationServerKey: ArrayBuffer | null;
  constructor(endpoint: string, applicationServerKey: ArrayBuffer | null) {
    this.endpoint = endpoint;
    this.applicationServerKey = applicationServerKey;
  }
  toJSON() { return { endpoint: this.endpoint, keys: { p256dh: 'P256', auth: 'AUTH' } }; }
  async unsubscribe() { this.unsubscribed = true; return true; }
}

class FakeEnvironment implements PushEnvironment {
  supported = true;
  current: NotificationPermission = 'default';
  answer: NotificationPermission = 'granted';
  asked = 0;
  subscription: FakeSubscription | null = null;
  subscribedWith: Uint8Array[] = [];
  permission() { return this.current; }
  async requestPermission() { this.asked += 1; this.current = this.answer; return this.answer; }
  async getSubscription() { return this.subscription; }
  async subscribe(key: Uint8Array<ArrayBuffer>) {
    this.subscribedWith.push(key);
    this.subscription = new FakeSubscription(`https://fcm.googleapis.com/fcm/send/${this.subscribedWith.length}`, key.buffer);
    return this.subscription;
  }
}

const device = (id: number, endpoint: string): PushDevice => ({
  id, endpoint, label: 'Chrome', receives_calendar: true, created_at: null, last_sent_at: null,
});

class FakeApi {
  config: PushConfig = { enabled: true, public_key: KEY };
  registered: PushDeviceRegistration[] = [];
  removed: number[] = [];
  api: PushApi = {
    config: async () => this.config,
    register: async (body) => { this.registered.push(body); return device(1, body.endpoint); },
    remove: async (id) => { this.removed.push(id); },
  };
}

describe('この端末で受け取る', () => {
  it('許可を求め、サーバの公開鍵で購読し、送り先と鍵と名前を登録する', async () => {
    const env = new FakeEnvironment();
    const server = new FakeApi();
    const result = await enableOnThisDevice(env, server.api, 'Chrome / Android');
    expect(result.state).toBe('on');
    expect(env.asked).toBe(1);
    expect(Array.from(env.subscribedWith[0])).toEqual([4, 1, 2]);
    expect(server.registered).toEqual([{
      endpoint: 'https://fcm.googleapis.com/fcm/send/1', keys: { p256dh: 'P256', auth: 'AUTH' }, label: 'Chrome / Android',
    }]);
  });

  it('サーバが送れない設定なら許可を求めない', async () => {
    const env = new FakeEnvironment();
    const server = new FakeApi();
    server.config = { enabled: false, public_key: null };
    expect((await enableOnThisDevice(env, server.api, 'x')).state).toBe('unavailable');
    expect(env.asked).toBe(0);
    expect(server.registered).toEqual([]);
  });

  it('使えないブラウザ・拒否されたときは購読しない', async () => {
    const unsupported = new FakeEnvironment();
    unsupported.supported = false;
    expect((await enableOnThisDevice(unsupported, new FakeApi().api, 'x')).state).toBe('unsupported');

    const denied = new FakeEnvironment();
    denied.answer = 'denied';
    const server = new FakeApi();
    expect((await enableOnThisDevice(denied, server.api, 'x')).state).toBe('denied');
    expect(denied.subscribedWith).toEqual([]);
    expect(server.registered).toEqual([]);

    const dismissed = new FakeEnvironment();
    dismissed.answer = 'default';
    expect((await enableOnThisDevice(dismissed, new FakeApi().api, 'x')).state).toBe('off');
  });

  it('同じ鍵の購読があれば使い回し、鍵が替わっていたら購読し直す', async () => {
    const env = new FakeEnvironment();
    env.current = 'granted';
    env.subscription = new FakeSubscription('https://fcm.googleapis.com/fcm/send/old', bytes(KEY));
    const server = new FakeApi();
    await enableOnThisDevice(env, server.api, 'x');
    expect(env.asked).toBe(0);
    expect(env.subscribedWith).toEqual([]);
    expect(server.registered[0].endpoint).toBe('https://fcm.googleapis.com/fcm/send/old');

    const stale = new FakeSubscription('https://fcm.googleapis.com/fcm/send/stale', bytes(OTHER_KEY));
    env.subscription = stale;
    await enableOnThisDevice(env, server.api, 'x');
    expect(stale.unsubscribed).toBe(true);
    expect(env.subscribedWith).toHaveLength(1);
    expect(server.registered[1].endpoint).toBe('https://fcm.googleapis.com/fcm/send/1');
  });
});

describe('この端末で止める', () => {
  it('サーバの登録を外し、ブラウザの購読もやめる（他の端末の登録は触らない）', async () => {
    const env = new FakeEnvironment();
    env.current = 'granted';
    const mine = new FakeSubscription('https://fcm.googleapis.com/fcm/send/mine', bytes(KEY));
    env.subscription = mine;
    const server = new FakeApi();
    await disableOnThisDevice(env, server.api, [device(7, 'https://other.example/x'), device(8, mine.endpoint)]);
    expect(server.removed).toEqual([8]);
    expect(mine.unsubscribed).toBe(true);
  });

  it('購読が無ければ何もしない', async () => {
    const server = new FakeApi();
    await disableOnThisDevice(new FakeEnvironment(), server.api, [device(7, 'x')]);
    expect(server.removed).toEqual([]);
  });
});

describe('この端末の状態', () => {
  it('サーバ・ブラウザ・許可・購読の順に見る', async () => {
    const env = new FakeEnvironment();
    expect((await thisDeviceState(env, false)).state).toBe('unavailable');
    expect((await thisDeviceState(env, true)).state).toBe('off');
    env.current = 'denied';
    expect((await thisDeviceState(env, true)).state).toBe('denied');
    env.current = 'granted';
    env.subscription = new FakeSubscription('https://fcm.googleapis.com/fcm/send/mine', null);
    expect(await thisDeviceState(env, true)).toEqual({ state: 'on', endpoint: 'https://fcm.googleapis.com/fcm/send/mine' });
    env.supported = false;
    expect((await thisDeviceState(env, true)).state).toBe('unsupported');
  });

  it('一覧からこの端末を送り先で見分ける', () => {
    const devices = [device(1, 'a'), device(2, 'b')];
    expect(thisDeviceOf(devices, 'b')?.id).toBe(2);
    expect(thisDeviceOf(devices, null)).toBeUndefined();
    expect(thisDeviceOf(devices, 'c')).toBeUndefined();
  });
});

describe('端末の名前', () => {
  it('ブラウザと OS から作る', () => {
    expect(deviceLabel('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36', true))
      .toBe('Chrome / Android (PWA)');
    expect(deviceLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36 Edg/129.0'))
      .toBe('Edge / Windows');
    expect(deviceLabel('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'))
      .toBe('Safari / iOS');
    expect(deviceLabel('Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0')).toBe('Firefox / Linux');
    expect(deviceLabel('')).toBe('Browser');
  });
});
