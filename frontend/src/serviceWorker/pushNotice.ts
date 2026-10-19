// 端末への通知（Web Push）の中身の読み方（task #193・ADR-0031）。Service Worker の束と試験から読む純関数だけを置く
// （⚠ 画面の束からは読まない。requestRoutes.ts と同じ理由で、読むと Service Worker が別の束を import して動かなくなる）。
//
// 中身はサーバ（src/infrastructure/push/web_push_sender.py の payload_of）が JSON で送る:
//   { title, body, url, tag, kind }
// 壊れていても通知は出す（Chrome は「通知を出さない push」を続けると購読を止めることがある）。

export interface PushNoticeData {
  title: string;
  body: string;
  /** 押したときに開く、このアプリの中のパス */
  url: string;
  /** 端末の通知の束ね札（同じ札は置き換わる） */
  tag: string | undefined;
  /** 通知の種類（`event_alarm` など。サーバの PushKind） */
  kind: string | undefined;
}

/**
 * 予定の通知の音を消す印の置き場（task #520・ADR-0052）。Service Worker は localStorage を読めないので、
 * 画面が Cache Storage にも写す。⚠ 画面側（preferences/alarmSound.ts）にも同じ値を書いている（束を分けるため import しない。試験で揃いを守る）
 */
export const ALARM_SOUND_CACHE = 'wbs-prefs';
export const ALARM_SOUND_KEY = '/__prefs/alarm-sound';
export const ALARM_SOUND_OFF = 'off';

/** 音なしで出す通知か。消してあるのは予定の通知の音だけ（ほかの通知は端末の設定どおり鳴る） */
export const isSilenced = (notice: Pick<PushNoticeData, 'kind'>, soundSetting: string | null | undefined): boolean =>
  notice.kind === 'event_alarm' && soundSetting === ALARM_SOUND_OFF;

export const FALLBACK_TITLE = 'WBS';
export const HOME_PATH = '/';

const asText = (value: unknown): string | undefined => (typeof value === 'string' ? value : undefined);

/**
 * 押したときに開く先。このアプリの中のパス（`/` で始まり `//` で始まらない）だけを通し、ほかは「今日」にする
 * （よそのサイトを開かせない）。
 */
export const safeAppPath = (value: unknown): string => {
  const path = asText(value);
  if (path == null || !path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return HOME_PATH;
  return path;
};

/** push の中身（文字列）を読む。読めなければ既定の題で出す */
export const parsePushPayload = (text: string | null | undefined): PushNoticeData => {
  let raw: Record<string, unknown> = {};
  if (text) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed != null && typeof parsed === 'object') raw = parsed as Record<string, unknown>;
    } catch {
      raw = { body: text };
    }
  }
  return {
    title: asText(raw.title) || FALLBACK_TITLE,
    body: asText(raw.body) ?? '',
    url: safeAppPath(raw.url),
    tag: asText(raw.tag),
    kind: asText(raw.kind),
  };
};
