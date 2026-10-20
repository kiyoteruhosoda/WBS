// 月の暦で日を押して休みを切り替える（task #557 / ADR-0059。プロジェクトのカレンダー・人のカレンダー）。
// 色だけに頼らず、日の下に短い言葉（「休日」「半休」など）を出し、読み上げにも同じ言葉を入れる。
import React from 'react';
import { Box, IconButton } from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { useI18n } from '../../i18n';
import { ds } from '../../theme';

export interface DayMark {
  /** off: 休み（終日）／half: 半日・短い日／work: 稼働日・出勤・残業／inherited: 親・プロジェクトから引き継いだもの／quiet: 稼働しない曜日など */
  tone: 'off' | 'half' | 'work' | 'inherited' | 'quiet';
  /** 日の下に出す短い言葉 */
  label: string;
}

interface Props {
  /** 表示する月（1 日） */
  month: Date;
  onMonthChange: (month: Date) => void;
  markOf: (day: string) => DayMark | null;
  /** 押せない日（引き継いだ休みなど）。省くとすべて押せる */
  isLocked?: (day: string) => boolean;
  /** 押した日と、押したボタン（小さなメニューを出す場所） */
  onPick: (day: string, anchor: HTMLElement) => void;
  disabled?: boolean;
  ariaLabel: string;
}

export const isoDay = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const TONES: Record<DayMark['tone'], { bg: string; fg: string; border: string }> = {
  off: { bg: ds.dangerPale, fg: ds.dangerText, border: ds.danger },
  half: { bg: ds.warnPale, fg: ds.warnText, border: ds.warnText },
  work: { bg: ds.successPale2, fg: ds.text, border: ds.success },
  inherited: { bg: ds.track, fg: ds.textSub, border: ds.border },
  quiet: { bg: 'transparent', fg: ds.textMuted, border: ds.borderPale },
};

// 月曜はじまり（weekdays は日曜はじまりの並び）
const MONDAY_FIRST = [1, 2, 3, 4, 5, 6, 0];

const MonthCalendarPicker: React.FC<Props> = ({
  month, onMonthChange, markOf, isLocked, onPick, disabled = false, ariaLabel,
}) => {
  const { t, weekdays } = useI18n();
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const lead = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ];
  const shift = (n: number) => onMonthChange(new Date(month.getFullYear(), month.getMonth() + n, 1));

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <IconButton size="small" aria-label={t('monthPicker.prev')} onClick={() => shift(-1)}>
          <ChevronLeftIcon fontSize="small" />
        </IconButton>
        <Box aria-live="polite" sx={{ fontSize: 14, fontWeight: 700, minWidth: 96, textAlign: 'center' }}>
          {t('monthPicker.title', { year: month.getFullYear(), month: month.getMonth() + 1 })}
        </Box>
        <IconButton size="small" aria-label={t('monthPicker.next')} onClick={() => shift(1)}>
          <ChevronRightIcon fontSize="small" />
        </IconButton>
      </Box>
      <Box role="group" aria-label={ariaLabel} sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: '4px' }}>
        {MONDAY_FIRST.map((dow) => (
          <Box key={dow} aria-hidden sx={{
            fontSize: 11, textAlign: 'center', fontWeight: 700,
            color: dow === 0 ? ds.dangerText : dow === 6 ? ds.primary : ds.textSub,
          }}>
            {weekdays[dow]}
          </Box>
        ))}
        {cells.map((d, i) => {
          if (!d) return <Box key={`e${i}`} aria-hidden />;
          const day = isoDay(d);
          const mark = markOf(day);
          const locked = isLocked?.(day) ?? false;
          const tone = mark ? TONES[mark.tone] : null;
          const name = t('monthPicker.dayLabel', { month: d.getMonth() + 1, day: d.getDate(), weekday: weekdays[d.getDay()] });
          return (
            <Box
              key={day}
              component="button"
              type="button"
              disabled={disabled || locked}
              aria-label={mark ? `${name} ${mark.label}` : name}
              onClick={(e: React.MouseEvent<HTMLElement>) => onPick(day, e.currentTarget)}
              sx={{
                minHeight: 44, p: '2px', borderRadius: '6px', font: 'inherit', cursor: disabled || locked ? 'default' : 'pointer',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1px',
                bgcolor: tone?.bg ?? ds.paper, color: tone?.fg ?? ds.text,
                border: `1px solid ${tone?.border ?? ds.borderPale}`,
                '&:focus-visible': { outline: `3px solid ${ds.primary}`, outlineOffset: '1px' },
                '&:disabled': { opacity: 1 },
              }}
            >
              <Box component="span" sx={{ fontSize: 13, fontWeight: mark && mark.tone !== 'quiet' ? 700 : 400 }}>{d.getDate()}</Box>
              {mark && (
                <Box component="span" sx={{ fontSize: 10, lineHeight: 1.1, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {mark.label}
                </Box>
              )}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

export default MonthCalendarPicker;
