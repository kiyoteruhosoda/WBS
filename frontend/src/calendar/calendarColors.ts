// カレンダーの色（移植元 `WinUI/Resources/Styles/Colors.xaml` と `Presentation/Helpers/WinColors.cs`）。
// 明暗のテーマごとの値は MUI のテーマ（`theme.palette.calendar`）に載せ、部品はそこから読む。

import type { EventColorKey } from '../types';

export interface CalendarPalette {
  surface: string;
  surfaceVariant: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  outOfMonthText: string;
  holidayBg: string;
  /** 会社の公休の日の地（ADR-0029） */
  companyDayOffBg: string;
  /** 私の休みの日の地 */
  personalDayOffBg: string;
  /** 曜日の休み（営業日の層の曜日に当たらない平日）の地 */
  weeklyOffBg: string;
  sundayBg: string;
  saturdayBg: string;
  /**
   * 過ぎた日・時刻に敷く半透明の黒（移植元は #3D000000 / #54000000。濃すぎて題名が読めないので薄くした）。
   * 予定のチップはこの上に描き、文字は白のまま地だけ `pastEventFactor` 倍に沈める。
   */
  pastShade: string;
  /** 過ぎた予定の地の色に掛ける倍率（影と同じ濃さ。`1 − 影の不透明度`） */
  pastEventFactor: number;
  gridLine: string;
  gridHalfLine: string;
  currentTimeLine: string;
  /** 終日の予定がある日に敷く色 */
  allDayTint: string;
  /** 予定の既定色・今日の丸・土曜の文字 */
  blue: string;
  /** 祝日のチップ・日曜の文字 */
  red: string;
  /** 祝日の日付の文字（暗いテーマでは明るい赤） */
  holidayText: string;
  selectedCircle: string;
  weekHeaderText: string;
  /** 色の上に載せる文字（予定のチップ・今日の丸） */
  onColor: string;
  /** ドラッグ中の行き先に描く半透明の青（移植元 GCalDragGhost） */
  dragGhost: string;
}

export const calendarPalettes: Record<'light' | 'dark', CalendarPalette> = {
  light: {
    surface: '#ffffff',
    surfaceVariant: '#f8f9fa',
    textPrimary: '#202124',
    textSecondary: '#70757a',
    border: '#e0e0e0',
    outOfMonthText: '#bdbdbd',
    holidayBg: '#fff0f0',
    companyDayOffBg: '#fff4e0',
    personalDayOffBg: '#e8f5ec',
    weeklyOffBg: '#f1f3f4',
    sundayBg: '#fff8f8',
    saturdayBg: '#f0f4ff',
    pastShade: 'rgba(0, 0, 0, 0.1)',
    pastEventFactor: 0.9,
    gridLine: '#d0d7de',
    gridHalfLine: 'rgba(208, 215, 222, 0.35)', // #5AD0D7DE
    currentTimeLine: '#ea4335',
    allDayTint: 'rgba(26, 115, 232, 0.19)', // #301A73E8
    blue: '#1a73e8',
    red: '#d93025',
    holidayText: '#d93025',
    selectedCircle: '#70757a',
    weekHeaderText: '#5f6368',
    onColor: '#ffffff',
    dragGhost: 'rgba(26, 115, 232, 0.35)', // #5A1A73E8
  },
  dark: {
    surface: '#1e1e1e',
    surfaceVariant: '#2d2d2d',
    textPrimary: '#ffffff',
    textSecondary: '#9aa0a6',
    border: '#3c3c3c',
    outOfMonthText: '#555555',
    holidayBg: '#3a1a1a',
    companyDayOffBg: '#3a2c16',
    personalDayOffBg: '#17301f',
    weeklyOffBg: '#2a2a2a',
    sundayBg: '#2d1a1a',
    saturdayBg: '#1a1a2d',
    pastShade: 'rgba(0, 0, 0, 0.2)',
    pastEventFactor: 0.8,
    gridLine: '#454545',
    gridHalfLine: 'rgba(69, 69, 69, 0.31)', // #50454545
    currentTimeLine: '#ea4335',
    allDayTint: 'rgba(26, 115, 232, 0.19)',
    blue: '#1a73e8',
    red: '#d93025',
    holidayText: '#f28b82',
    selectedCircle: '#70757a',
    weekHeaderText: '#9aa0a6',
    onColor: '#ffffff',
    dragGhost: 'rgba(26, 115, 232, 0.35)', // #5A1A73E8
  },
};

/** 予定の色。白い文字を載せられる濃さなので、明暗どちらのテーマでも同じ値（移植元と同じ）。 */
export const eventColors: Record<EventColorKey, string> = {
  DEFAULT: '#1a73e8',
  TOMATO: '#d50000',
  TANGERINE: '#f4511e',
  BANANA: '#f6bf26',
  BASIL: '#0b8043',
  SAGE: '#33b679',
  PEACOCK: '#039be5',
  BLUEBERRY: '#3f51b5',
  LAVENDER: '#7986cb',
  GRAPE: '#8e24aa',
  GRAPHITE: '#616161',
};

export const eventColor = (key: EventColorKey | null | undefined): string => eventColors[key ?? 'DEFAULT'] ?? eventColors.DEFAULT;

/** 過ぎた予定の地の色（影を重ねたのと同じ色。文字は白のまま）。 */
export const pastEventColor = (hex: string, palette: Pick<CalendarPalette, 'pastEventFactor'>): string =>
  darken(hex, palette.pastEventFactor);

/** 予定の枠の色（地の色を 0.72 倍に暗くする。移植元 `DarkenColor`）。 */
export const darken = (hex: string, factor = 0.72): string => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return hex;
  const channel = (h: string) => Math.floor(parseInt(h, 16) * factor).toString(16).padStart(2, '0');
  return `#${channel(m[1])}${channel(m[2])}${channel(m[3])}`;
};

/**
 * 日の列の地（ADR-0029）。休みの層の帯があればその理由の色、曜日の休み（営業日の層が表示のとき）なら
 * 土日は今までの色・平日は曜日の休みの色。営業日の層を隠しているとき（`nonWorkdays` が null）は土日の色だけ。
 */
export const dayColumnBackground = (
  palette: Pick<CalendarPalette, 'holidayBg' | 'companyDayOffBg' | 'personalDayOffBg' | 'weeklyOffBg' | 'sundayBg' | 'saturdayBg'>,
  dow: number,
  holiday: { reason?: string } | undefined,
  nonWorkday: boolean | null,
): string => {
  // 曜日の休みの帯は地の色を変えない（下の曜日の休みの色のまま）
  if (holiday && holiday.reason !== 'WEEKLY') {
    if (holiday.reason === 'COMPANY') return palette.companyDayOffBg;
    if (holiday.reason === 'PERSONAL') return palette.personalDayOffBg;
    return palette.holidayBg;
  }
  if (nonWorkday === false) return 'transparent';
  if (dow === 0) return palette.sundayBg;
  if (dow === 6) return palette.saturdayBg;
  return nonWorkday ? palette.weeklyOffBg : 'transparent';
};

/**
 * プライベートの予定（ADR-0033）に重ねる斜線。地の色は予定の色のまま、白い細い斜線で仕事の予定と見分ける
 * （色だけに頼らない。題名の白い文字は読める濃さ）。
 */
export const PRIVATE_HATCH =
  'repeating-linear-gradient(135deg, rgba(255,255,255,0.32) 0 3px, rgba(255,255,255,0) 3px 8px)';

/** 回の地に重ねる模様（プライベートなら斜線、ほかは無し）。 */
export const occurrencePattern = (occurrence: { is_private?: boolean }): string =>
  (occurrence.is_private ? PRIVATE_HATCH : 'none');

