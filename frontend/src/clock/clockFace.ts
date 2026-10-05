// 時計の文字盤で時刻を選ぶ（task #287、ADR-0039）。DOM を見ない純関数だけを置く。
//
// - 表記: 24 時間（09:05）か 12 時間（午前 9:05）
// - 文字盤: 時は 12 時間なら外周の 1〜12、24 時間なら外周 0〜11・内周 12〜23。分は 5 分刻み。
//   押した点（文字盤の中心からの x, y。y は下が正）から値を出す。

export type ClockStyle = '24h' | '12h';

/** 分の刻み（文字盤で選べる分） */
export const DIAL_MINUTE_STEP = 5;
/** 24 時間の時の文字盤で、中心からこの割合より内側は内周（12〜23） */
export const INNER_RING_RATIO = 0.62;

const pad2 = (n: number): string => String(n).padStart(2, '0');

/** 0..1439 の分 → 表記どおりの文字。12 時間は `{am}`/`{pm}` を前に置く（日本語は「午前 9:05」）。 */
export const formatClockTime = (
  minuteOfDay: number,
  style: ClockStyle,
  labels: { am: string; pm: string },
): string => {
  const hour = Math.floor(minuteOfDay / 60);
  const minute = minuteOfDay % 60;
  if (style === '24h') return `${pad2(hour)}:${pad2(minute)}`;
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${hour < 12 ? labels.am : labels.pm} ${h12}:${pad2(minute)}`;
};

/** 12 時の方向から時計回りの角（0..360）。 */
const clockwiseAngle = (x: number, y: number): number => {
  const deg = (Math.atan2(x, -y) * 180) / Math.PI;
  return deg < 0 ? deg + 360 : deg;
};

/** 角 → 12 等分の位置（0 が 12 時の方向）。 */
const twelfthOf = (x: number, y: number): number => Math.round(clockwiseAngle(x, y) / 30) % 12;

/**
 * 時の文字盤の点 → 時（0..23）。12 時間は午前／午後を `pm` で決める（12 時の方向は 0 時か 12 時）。
 * 24 時間は外周が 0〜11（12 時の方向は 0）、内周が 12〜23（12 時の方向は 12）。
 */
export const hourAtPoint = (
  x: number, y: number, radius: number, style: ClockStyle, pm: boolean,
): number => {
  const pos = twelfthOf(x, y);
  if (style === '12h') return pos + (pm ? 12 : 0);
  const inner = Math.hypot(x, y) < radius * INNER_RING_RATIO;
  return inner ? pos + 12 : pos;
};

/** 分の文字盤の点 → 分（5 分刻み、0..55）。 */
export const minuteAtPoint = (x: number, y: number): number =>
  (Math.round(clockwiseAngle(x, y) / (360 / (60 / DIAL_MINUTE_STEP))) * DIAL_MINUTE_STEP) % 60;

/** 文字盤の目盛り 1 つ。`angle` は 12 時の方向から時計回り、`inner` は 24 時間の内周。 */
export interface DialMark {
  value: number;
  label: string;
  angle: number;
  inner: boolean;
}

/** 時の文字盤の目盛り。 */
export const hourMarks = (style: ClockStyle): DialMark[] => {
  if (style === '12h') {
    return Array.from({ length: 12 }, (_, i) => ({ value: i, label: String(i === 0 ? 12 : i), angle: i * 30, inner: false }));
  }
  return [
    ...Array.from({ length: 12 }, (_, i) => ({ value: i, label: pad2(i), angle: i * 30, inner: false })),
    ...Array.from({ length: 12 }, (_, i) => ({ value: i + 12, label: pad2(i + 12), angle: i * 30, inner: true })),
  ];
};

/** 分の文字盤の目盛り（5 分ごと）。 */
export const minuteMarks = (): DialMark[] =>
  Array.from({ length: 12 }, (_, i) => ({ value: i * 5, label: pad2(i * 5), angle: i * 30, inner: false }));

/** 針の角と、内周を指すか（選んでいる値から）。 */
export const handOf = (
  view: 'hour' | 'minute', minuteOfDay: number, style: ClockStyle,
): { angle: number; inner: boolean } => {
  const hour = Math.floor(minuteOfDay / 60);
  const minute = minuteOfDay % 60;
  if (view === 'minute') return { angle: minute * 6, inner: false };
  return { angle: (hour % 12) * 30, inner: style === '24h' && hour >= 12 };
};
