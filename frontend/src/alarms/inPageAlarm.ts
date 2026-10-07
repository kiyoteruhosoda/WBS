// 画面の中で予定を知らせる（task #312、ADR-0041）。DOM を見ない純関数だけを置く。
//
// ブラウザの通知が使えない端末（会社の PC で管理者が通知を止めている）でも、WBS を開いている間は
// 画面の中の表示と音で知らせる。通知の一覧はサーバの `GET /api/calendar/alarms`（ADR-0021）を引き、
// 鳴らす規則も ADR-0021 と同じ（`notify_at` より早くは鳴らさない・1 分までの遅れは鳴らす・それより遅れたら鳴らさない）。
import type { CalendarAlarm } from '../api/calendar';
import type { PushDevice } from '../api/push';

/** 遅れてもこの間は鳴らす（ADR-0021 の「1 分以内」） */
export const DUE_GRACE_MS = 60_000;
/**
 * 通知の一覧を引き直す間隔。1 分の猶予と同じにして、作ったばかりの・別の端末で直した予定も、
 * 知らせる時刻が 1 分より先なら間に合わせる
 */
export const FETCH_EVERY_MS = 60_000;
/** 1 回に引く先の長さ。引き直す間隔より長くして、1 回引けなくても次の分まで持たせる */
export const LOOKAHEAD_MS = 20 * 60_000;
/** 鳴らした印を覚えておく長さ（それより古い印は捨てる） */
export const RUNG_KEEP_MS = 24 * 60 * 60_000;

/** 今鳴らすべきか（`notify_at ≤ now ≤ notify_at + 1 分`） */
export const isDue = (alarm: Pick<CalendarAlarm, 'notify_at'>, nowMs: number): boolean => {
  const at = Date.parse(alarm.notify_at);
  return at <= nowMs && nowMs <= at + DUE_GRACE_MS;
};

/** 引く期間。取りこぼしを拾うため、始まりは「今 − 1 分」（ADR-0021） */
export const alarmWindow = (nowMs: number): { from: string; to: string } => ({
  from: new Date(nowMs - DUE_GRACE_MS).toISOString(),
  to: new Date(nowMs + LOOKAHEAD_MS).toISOString(),
});

/** 一覧のうち、今鳴らすもの（この画面でもう出したものは除く） */
export const dueAlarms = (
  alarms: readonly CalendarAlarm[], nowMs: number, seen: ReadonlySet<string>,
): CalendarAlarm[] => alarms.filter((alarm) => !seen.has(alarm.id) && isDue(alarm, nowMs));

/**
 * 出している知らせに 1 件足す。同じ回の前の知らせ（15 分前 → 5 分前…）は新しいものに置き換える
 * （閉じずにいても同じ予定が何枚も並ばない）。
 */
export const withNotice = (shown: readonly CalendarAlarm[], alarm: CalendarAlarm): CalendarAlarm[] => [
  ...shown.filter((notice) => notice.occurrence_id !== alarm.occurrence_id),
  alarm,
];

/**
 * この端末で Web Push の予定の通知を受け取っているか（受け取っているなら画面の中では鳴らさない）。
 * サーバが送れる・この端末の購読がサーバの一覧にあり予定の通知を受ける・「予定の通知」を知らせる、のすべて。
 */
export const pushCoversAlarms = (input: {
  serverEnabled: boolean;
  /** このブラウザの購読の送り先（許可が無い・購読していなければ null） */
  endpoint: string | null;
  devices: readonly PushDevice[];
  eventAlarm: boolean;
}): boolean => {
  if (!input.serverEnabled || input.endpoint == null || !input.eventAlarm) return false;
  const mine = input.devices.find((device) => device.endpoint === input.endpoint);
  return mine?.receives_calendar ?? false;
};

/** 鳴らした印（通知の id → 鳴らした瞬間）。タブ同士で共有する */
export type RungLog = Record<string, number>;

export const parseRungLog = (raw: string | null): RungLog => {
  if (!raw) return {};
  try {
    const value: unknown = JSON.parse(raw);
    if (value == null || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).filter((entry): entry is [string, number] => typeof entry[1] === 'number'),
    );
  } catch {
    return {};
  }
};

/**
 * 鳴らす役を取る。まだ誰も鳴らしていなければ印を付けて `claimed: true`、付いていれば false。
 * 古い印は捨てる。⚠ 読んで書くまでを 1 つのタブだけが通るように、呼ぶ側が鍵（Web Locks）で包む。
 */
export const claimRing = (log: RungLog, id: string, nowMs: number): { claimed: boolean; log: RungLog } => {
  const kept = Object.fromEntries(Object.entries(log).filter(([, at]) => nowMs - at < RUNG_KEEP_MS));
  if (id in kept) return { claimed: false, log: kept };
  return { claimed: true, log: { ...kept, [id]: nowMs } };
};

/** 知らせの文言の鍵と引数（開始の何分前か） */
export const noticeLead = (
  alarm: Pick<CalendarAlarm, 'minutes_before'>,
): { key: 'inPageAlarm.startsIn' | 'inPageAlarm.startsNow'; params: { minutes: number } } => (
  alarm.minutes_before > 0
    ? { key: 'inPageAlarm.startsIn', params: { minutes: alarm.minutes_before } }
    : { key: 'inPageAlarm.startsNow', params: { minutes: 0 } }
);

/** タブの題名の点滅。偶数の拍は知らせ、奇数の拍は元の題名 */
export const blinkingTitle = (original: string, notice: string, beat: number): string =>
  (beat % 2 === 0 ? notice : original);
