// Calendar colors (ported from `WinUI/Resources/Styles/Colors.xaml` and `Presentation/Helpers/WinColors.cs`).
// Per light/dark theme values live in the MUI theme (`theme.palette.calendar`) and components read them from there.

import type { EventColorKey } from '../types';

export interface CalendarPalette {
  surface: string;
  surfaceVariant: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  outOfMonthText: string;
  holidayBg: string;
  /** Background of company holidays (ADR-0029) */
  companyDayOffBg: string;
  /** Background of my days off */
  personalDayOffBg: string;
  /** Background of weekday days off (weekdays not in the working-day layer's weekdays) */
  weeklyOffBg: string;
  sundayBg: string;
  saturdayBg: string;
  /**
   * Translucent black laid over past days/times (the original used #3D000000 / #54000000; lightened because titles were unreadable).
   * Event chips are drawn on top; text stays white and only the background is darkened by `pastEventFactor`.
   */
  pastShade: string;
  /** Factor applied to the background of past events (same depth as the shade: `1 − shade opacity`) */
  pastEventFactor: number;
  gridLine: string;
  gridHalfLine: string;
  currentTimeLine: string;
  /** Color laid on days with all-day events */
  allDayTint: string;
  /** Default event color, today's circle, Saturday text */
  blue: string;
  /** Holiday chips, Sunday text */
  red: string;
  /** Holiday date text (bright red in the dark theme) */
  holidayText: string;
  selectedCircle: string;
  weekHeaderText: string;
  /** Text drawn on top of colors (event chips, today's circle) */
  onColor: string;
  /** Translucent blue drawn at the drag target (ported GCalDragGhost) */
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

/** Event colors. Dark enough for white text, so the same values in both themes (as in the original). */
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

/** Background color of past events (same as with the shade applied; text stays white). */
export const pastEventColor = (hex: string, palette: Pick<CalendarPalette, 'pastEventFactor'>): string =>
  darken(hex, palette.pastEventFactor);

/** Event border color (background darkened ×0.72; ported `DarkenColor`). */
export const darken = (hex: string, factor = 0.72): string => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return hex;
  const channel = (h: string) => Math.floor(parseInt(h, 16) * factor).toString(16).padStart(2, '0');
  return `#${channel(m[1])}${channel(m[2])}${channel(m[3])}`;
};

/**
 * Day column background (ADR-0029). The reason's color if there is a day-off band; for weekday days off (when the working-day layer is shown),
 * weekends keep their usual color and weekdays get the weekday day-off color. With the working-day layer hidden (`nonWorkdays` is null), only weekend colors.
 */
export const dayColumnBackground = (
  palette: Pick<CalendarPalette, 'holidayBg' | 'companyDayOffBg' | 'personalDayOffBg' | 'weeklyOffBg' | 'sundayBg' | 'saturdayBg'>,
  dow: number,
  holiday: { reason?: string } | undefined,
  nonWorkday: boolean | null,
): string => {
  // Weekday day-off bands don't change the background (keeps the weekday day-off color below)
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
 * Hatching over private events (ADR-0033). The background keeps the event color; thin white diagonal lines set them apart from work events
 * (not relying on color alone; white title text stays readable).
 */
export const PRIVATE_HATCH =
  'repeating-linear-gradient(135deg, rgba(255,255,255,0.32) 0 3px, rgba(255,255,255,0) 3px 8px)';

/** Pattern over an occurrence's background (hatching if private, none otherwise). */
export const occurrencePattern = (occurrence: { is_private?: boolean }): string =>
  (occurrence.is_private ? PRIVATE_HATCH : 'none');

