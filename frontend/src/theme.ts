import { createTheme } from '@mui/material/styles';

// デジタル庁デザインシステム準拠トークン（design handoff README 参照）
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

// カテゴリ色（API の color 未設定時のフォールバック）
export const categoryPalette = ['#0017C1', '#1E8E4E', '#B26C00', '#6B7280', '#6B46C1'] as const;

export const categoryColor = (categoryId: number | null | undefined, apiColor?: string | null): string => {
  if (apiColor) return apiColor;
  if (categoryId == null) return categoryPalette[3];
  return categoryPalette[(categoryId - 1 + categoryPalette.length * 100) % categoryPalette.length];
};

export const fontFamily = "'Noto Sans JP', system-ui, sans-serif";

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
  },
  typography: {
    fontFamily,
    fontSize: 14,
    h5: { fontSize: 22, fontWeight: 700 },
    h6: { fontSize: 16, fontWeight: 700 },
    subtitle2: { fontSize: 13, fontWeight: 700 },
    body1: { fontSize: 14 },
    body2: { fontSize: 13 },
    caption: { fontSize: 12 },
    button: { fontWeight: 700, fontSize: 14 },
  },
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
