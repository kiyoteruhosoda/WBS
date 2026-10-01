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
  sundayBg: string;
  saturdayBg: string;
  /** 過ぎた日・時刻に重ねる半透明の黒 */
  pastShade: string;
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
    sundayBg: '#fff8f8',
    saturdayBg: '#f0f4ff',
    pastShade: 'rgba(0, 0, 0, 0.24)', // #3D000000
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
    sundayBg: '#2d1a1a',
    saturdayBg: '#1a1a2d',
    pastShade: 'rgba(0, 0, 0, 0.33)', // #54000000
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

/** 予定の枠の色（地の色を 0.72 倍に暗くする。移植元 `DarkenColor`）。 */
export const darken = (hex: string, factor = 0.72): string => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return hex;
  const channel = (h: string) => Math.floor(parseInt(h, 16) * factor).toString(16).padStart(2, '0');
  return `#${channel(m[1])}${channel(m[2])}${channel(m[3])}`;
};
