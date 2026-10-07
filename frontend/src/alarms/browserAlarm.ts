// 画面の中で知らせるための、ブラウザの道具（task #312、ADR-0041）。規則は inPageAlarm.ts の純関数が持つ。
//
// - 拍（ticker）: 裏のタブではページのタイマーが間引かれる（5 分を超えると 1 分に 1 回）。専用の Worker の
//   タイマーは間引かれないので、Worker から 1 秒ごとに拍を送ってもらう。Worker が作れなければページのタイマーで代える
// - 鳴らした印（ledger）: タブ同士で localStorage に共有し、読んで書くまでを Web Locks で 1 タブずつにする
// - 音（chime）: WebAudio で作る（音声ファイルを足さない）。⚠ ブラウザは、画面を 1 度も押していないタブの音を止める
// - 閉じた知らせ（channel）: BroadcastChannel で、ほかのタブの同じ知らせも閉じる
import { claimRing, parseRungLog } from './inPageAlarm';

/** 1 秒ごとに `onTick` を呼ぶ。戻り値で止める */
export const startTicker = (onTick: () => void, everyMs = 1000): (() => void) => {
  try {
    const url = URL.createObjectURL(
      new Blob([`setInterval(function () { postMessage(0); }, ${everyMs});`], { type: 'text/javascript' }),
    );
    const worker = new Worker(url);
    worker.onmessage = () => onTick();
    return () => {
      worker.terminate();
      URL.revokeObjectURL(url);
    };
  } catch {
    const id = window.setInterval(onTick, everyMs);
    return () => window.clearInterval(id);
  }
};

const RUNG_KEY = 'wbs.inPageAlarm.rung';
const LOCK_NAME = 'wbs-in-page-alarm';

/** 鳴らす役を取る（取れたタブだけが鳴らす）。localStorage が使えなければ、そのタブは取れたとみなす */
export const claimRingOnThisDevice = async (id: string, nowMs: number): Promise<boolean> => {
  const run = (): boolean => {
    let raw: string | null = null;
    try {
      raw = window.localStorage.getItem(RUNG_KEY);
    } catch {
      // 読めなければ空とみなす
    }
    const { claimed, log } = claimRing(parseRungLog(raw), id, nowMs);
    try {
      if (claimed) window.localStorage.setItem(RUNG_KEY, JSON.stringify(log));
    } catch {
      // 覚えられないだけ（ほかのタブも鳴らすことがある）
    }
    return claimed;
  };
  if ('locks' in navigator && navigator.locks) return navigator.locks.request(LOCK_NAME, run);
  return run();
};

const wait = (ms: number) => new Promise<void>((resolve) => { window.setTimeout(resolve, ms); });

/** 呼び鈴の音（3 音を 3 回）。 */
export class Chime {
  private context: AudioContext | null = null;

  private ensure(): AudioContext | null {
    if (this.context) return this.context;
    try {
      this.context = new AudioContext();
    } catch {
      this.context = null;
    }
    return this.context;
  }

  /** 画面を押したときに呼ぶ（このときだけ、ブラウザは音を出す許しをくれる） */
  unlock(): void {
    const context = this.ensure();
    if (context && context.state !== 'running') void context.resume().catch(() => undefined);
  }

  /** 今すぐ音を出せるか */
  get ready(): boolean {
    return this.context?.state === 'running';
  }

  /** 鳴らす。出せなかったら false（画面を 1 度も押していないタブ） */
  async play(): Promise<boolean> {
    const context = this.ensure();
    if (!context) return false;
    if (context.state !== 'running') {
      // 許しが無いと resume は返ってこないことがある。待ちすぎない
      await Promise.race([context.resume().catch(() => undefined), wait(500)]);
    }
    if (context.state !== 'running') return false;
    const notes = [1318.5, 1046.5, 784.0]; // ミ・ド・ソ
    const start = context.currentTime + 0.05;
    for (let round = 0; round < 3; round += 1) {
      notes.forEach((frequency, i) => {
        const at = start + round * 1.4 + i * 0.22;
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.35, at + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.7);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start(at);
        oscillator.stop(at + 0.75);
      });
    }
    return true;
  }
}

export type AlarmChannelMessage = { type: 'dismiss'; occurrenceId: string; alarmId: string };

/** タブ同士の知らせ。BroadcastChannel が無いブラウザでは何もしない */
export const openAlarmChannel = (
  onMessage: (message: AlarmChannelMessage) => void,
): { post: (message: AlarmChannelMessage) => void; close: () => void } => {
  if (typeof BroadcastChannel === 'undefined') return { post: () => undefined, close: () => undefined };
  const channel = new BroadcastChannel('wbs-in-page-alarm');
  channel.onmessage = (event: MessageEvent<AlarmChannelMessage>) => {
    if (event.data?.type === 'dismiss') onMessage(event.data);
  };
  return { post: (message) => channel.postMessage(message), close: () => channel.close() };
};
