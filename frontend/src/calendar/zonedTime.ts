// 閲覧者のタイムゾーンでの「日」と「分」。
//
// カレンダーの部品は、日付を `YYYY-MM-DD` の文字列、時刻をその日の 0:00 からの分で持つ。
// ブラウザのローカル（`Date#getHours` など）には頼らない——利用者設定のタイムゾーンは
// ブラウザのものと違いうる（`utils/format.ts` の `activeTimeZone`）。瞬間 → 壁時計は Intl で、
// 日付の足し引きは UTC の暦で行うので、実行環境の TZ に結果が左右されない。

export const MINUTES_PER_DAY = 24 * 60;

/** ある瞬間の、あるタイムゾーンでの壁時計。 */
export interface ZonedPoint {
  date: string; // YYYY-MM-DD
  minute: number; // 0..1439
}

const formatters = new Map<string, Intl.DateTimeFormat>();

const formatterFor = (timeZone: string): Intl.DateTimeFormat => {
  let f = formatters.get(timeZone);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    });
    formatters.set(timeZone, f);
  }
  return f;
};

/** 不正・未設定のタイムゾーンはブラウザのものへ落とす。 */
export const resolveTimeZone = (timeZone: string | null | undefined): string => {
  if (timeZone) {
    try {
      formatterFor(timeZone);
      return timeZone;
    } catch {
      // 下へ
    }
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
};

const pad2 = (n: number): string => String(n).padStart(2, '0');

const ymd = (y: number, m: number, d: number): string => `${String(y).padStart(4, '0')}-${pad2(m)}-${pad2(d)}`;

/** UTC の瞬間（ミリ秒）を、そのタイムゾーンの日と分へ。 */
export const toZonedPoint = (instantMs: number, timeZone: string): ZonedPoint => {
  const parts = formatterFor(timeZone).formatToParts(new Date(instantMs));
  const get = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(parts.find((p) => p.type === type)?.value ?? 0);
  return {
    date: ymd(get('year'), get('month'), get('day')),
    minute: (get('hour') % 24) * 60 + get('minute'),
  };
};

const parseYmd = (date: string): [number, number, number] => {
  const [y, m, d] = date.split('-').map(Number);
  return [y, m, d];
};

const utcDay = (date: string): number => {
  const [y, m, d] = parseYmd(date);
  return Date.UTC(y, m - 1, d);
};

const fromUtcDay = (ms: number): string => {
  const d = new Date(ms);
  return ymd(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
};

/**
 * そのタイムゾーンの壁時計（日 ＋ 分）を UTC の瞬間（ミリ秒）へ。
 * 画面の入力（開始日・開始時刻）を API の `start`（UTC）へ直すときに使う。
 * DST の重なりは先の方、隙間は後ろへ送った時刻になる。
 */
export const fromZonedPoint = (date: string, minute: number, timeZone: string): number => {
  const wall = utcDay(date) + minute * 60_000;
  let guess = wall;
  // オフセットを 2 度当て直せば、DST の境目以外は 1 度目で、境目でも 2 度目で落ち着く。
  for (let i = 0; i < 2; i++) {
    const p = toZonedPoint(guess, timeZone);
    const seen = utcDay(p.date) + p.minute * 60_000;
    guess += wall - seen;
  }
  return guess;
};

export const addDays = (date: string, days: number): string => fromUtcDay(utcDay(date) + days * 86_400_000);

/** b − a（日）。 */
export const diffDays = (a: string, b: string): number => Math.round((utcDay(b) - utcDay(a)) / 86_400_000);

/** 0 = 日曜 … 6 = 土曜。 */
export const dayOfWeek = (date: string): number => new Date(utcDay(date)).getUTCDay();

export const dayOfMonth = (date: string): number => parseYmd(date)[2];

/** その日を含む月の 1 日。 */
export const firstOfMonth = (date: string): string => {
  const [y, m] = parseYmd(date);
  return ymd(y, m, 1);
};

/** 月を足す（結果は常にその月の 1 日）。 */
export const addMonths = (monthFirst: string, months: number): string => {
  const [y, m] = parseYmd(monthFirst);
  const index = y * 12 + (m - 1) + months;
  return ymd(Math.floor(index / 12), (index % 12) + 1, 1);
};

export const yearMonthOf = (date: string): { year: number; month: number } => {
  const [y, m] = parseYmd(date);
  return { year: y, month: m };
};

/** `HH:MM`。1440 は表示専用の `24:00`（time-model §7）。 */
export const formatMinute = (minute: number): string => `${pad2(Math.floor(minute / 60))}:${pad2(minute % 60)}`;
