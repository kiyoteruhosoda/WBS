import { createTheme } from '@mui/material/styles';
import type { ThemeOptions } from '@mui/material/styles';
import { calendarPalettes } from './calendar/calendarColors';
import type { CalendarPalette } from './calendar/calendarColors';

// Put the calendar colors (light/dark) on the theme. Components read `theme.palette.calendar`.
declare module '@mui/material/styles' {
  interface Palette {
    calendar: CalendarPalette;
  }
  interface PaletteOptions {
    calendar?: CalendarPalette;
  }
}

// Tokens following the Digital Agency design system (see the design handoff README)
export const ds = {
  primary: '#0017C1',
  primaryHover: '#000EA5',
  primaryPale: '#E6EAFB',
  primaryPaleBorder: '#B8C4F0',
  text: '#1A1A1C',
  textSub: '#5A5A5C',
  textMuted: '#767678',
  border: '#D8D8D8',
  borderInput: '#767678',
  borderPale: '#E4E4E6',
  borderFaint: '#EEEEEE',
  hairline: '#F2F2F2',
  canvas: '#F2F2F2',
  paper: '#FFFFFF',
  success: '#1E8E4E',
  successDark: '#1E7A45',
  successPale: '#E1F1E8',
  successPale2: '#DDF1E6',
  danger: '#EC0000',
  dangerText: '#C4291C',
  dangerPale: '#FDECEC',
  dangerPale2: '#FCE9E7',
  dangerPale3: '#FBE4E2',
  dangerPaleBorder: '#F1C6C6',
  warnText: '#8A5A00',
  warnPale: '#FBEFD6',
  todoGray: '#B7B7BB',
  track: '#EAEAEC',
  priorityHighText: '#B3261E',
  priorityHighBg: '#FCE9E7',
  priorityLowText: '#41474D',
  priorityLowBg: '#EEEEEF',
  rowHighlight: '#F4F7FF',
  ganttDoingTrack: '#DCE3FA',
  ganttLateTrack: '#FBE0E0',
} as const;

// Category colors (fallback when the API color is unset). ⚠ Do not change order or count
// —— uncolored categories get one of these 5 colors by id, so adding more changes existing colors.
const fallbackPalette = ['#0017C1', '#1E8E4E', '#B26C00', '#6B7280', '#6B46C1'] as const;

// Colors selectable for categories and projects. Orange shades added (2026-10-02, owner's request).
// All are dark enough to read white text on.
export const categoryPalette = [
  ...fallbackPalette,
  '#E8590C', // orange
  '#D9480F', // dark orange
  '#F08C00', // amber
  '#C92A2A', // red
  '#C2255C', // crimson
  '#0C8599', // teal
] as const;

export const categoryColor = (categoryId: number | null | undefined, apiColor?: string | null): string => {
  if (apiColor) return apiColor;
  if (categoryId == null) return fallbackPalette[3];
  return fallbackPalette[(categoryId - 1 + fallbackPalette.length * 100) % fallbackPalette.length];
};

export const fontFamily = "'Noto Sans JP', system-ui, sans-serif";
// WBS fonts (task #639, ADR-0061): headings in bold gothic, WBS codes and dates monospaced (digits align). Body text stays Noto Sans JP
export const headingFont = "'Zen Kaku Gothic New', 'Noto Sans JP', system-ui, sans-serif";
export const codeFont = "'IBM Plex Mono', ui-monospace, Menlo, monospace";

const typography: ThemeOptions['typography'] = {
  fontFamily,
  fontSize: 14,
  h5: { fontSize: 22, fontWeight: 700, fontFamily: headingFont },
  h6: { fontSize: 16, fontWeight: 700, fontFamily: headingFont },
  subtitle2: { fontSize: 13, fontWeight: 700 },
  body1: { fontSize: 14 },
  body2: { fontSize: 13 },
  caption: { fontSize: 12 },
  button: { fontWeight: 700, fontSize: 14 },
};

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: ds.primary, dark: ds.primaryHover },
    success: { main: ds.success, dark: ds.successDark },
    error: { main: ds.danger },
    warning: { main: ds.warnText },
    text: { primary: ds.text, secondary: ds.textSub },
    divider: ds.border,
    background: { default: ds.canvas, paper: ds.paper },
    calendar: calendarPalettes.light,
  },
  typography,
  shape: { borderRadius: 8 },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { textTransform: 'none', borderRadius: 8, padding: '9px 20px', lineHeight: 1.5 },
        contained: {
          '&.MuiButton-colorPrimary:hover': { backgroundColor: ds.primaryHover },
        },
        outlined: {
          '&.MuiButton-colorPrimary': { borderWidth: 1.5 },
          '&.MuiButton-colorPrimary:hover': { borderWidth: 1.5, backgroundColor: ds.primaryPale },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          backgroundColor: ds.paper,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: ds.borderInput },
        },
      },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        outlined: { borderColor: ds.border },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: { fontWeight: 700, fontSize: 13, color: ds.textSub, backgroundColor: '#F7F7F8' },
        root: { borderBottomColor: '#ECECEE' },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 700 },
      },
    },
  },
});

// Dark theme (calendar components can render with the dark side of `palette.calendar`). No screen uses it yet.
// Other screens hard-code the light `ds` colors, so darkening the whole app is a separate task.
export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#8ab4f8' },
    background: { default: calendarPalettes.dark.surface, paper: calendarPalettes.dark.surface },
    calendar: calendarPalettes.dark,
  },
  typography,
  shape: { borderRadius: 8 },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { textTransform: 'none', borderRadius: 8, lineHeight: 1.5 } },
    },
    MuiPaper: { defaultProps: { elevation: 0 } },
  },
});
