// 締めの工数表（task #389、ADR-0047）。行はプロジェクト（名前の下にプロジェクトコード）、列は日、行と日の計。
// いちばん上の行は、その日の業務の開始と終了（休憩は差し引かない）。時間は 0.5 時間単位で見せ、
// 正確な長さは吹き出しで出す。WinTrack の自動の打刻を含むセルに点を付ける。セルを押すと、その日・その行の打刻の一覧。
import React from 'react';
import { Box, ButtonBase } from '@mui/material';
import { useI18n } from '../../i18n';
import type { Ledger, LedgerRow } from '../../closing/closingLedger';
import { formatHalfHours } from '../../closing/closingLedger';
import { dayOfWeek, formatMinute } from '../../calendar/zonedTime';
import { formatExactDuration } from '../../utils/format';
import { ds } from '../../theme';

interface Props {
  ledger: Ledger;
  onOpenCell: (date: string, row: LedgerRow) => void;
}

const cell = { px: '10px', py: '8px', fontSize: 13, borderBottom: `1px solid ${ds.borderFaint}`, whiteSpace: 'nowrap' } as const;
const sticky = { position: 'sticky', left: 0, bgcolor: ds.paper, zIndex: 1 } as const;
const numeric = { fontVariantNumeric: 'tabular-nums', textAlign: 'right' } as const;
/** 自動の打刻の印（WinTrack の青緑） */
const AUTO_COLOR = '#0d7377';

const LedgerTable: React.FC<Props> = ({ ledger, onOpenCell }) => {
  const { t, weekdays } = useI18n();
  const labelOf = (row: LedgerRow): string => {
    switch (row.kind) {
      case 'direct': return t('closing.totalsDirect', { name: row.title ?? '' });
      case 'unclassified': return t('closing.totalsUnclassified');
      case 'outside': return t('closing.totalsOutside');
      case 'unassigned': return t('closing.unassigned');
      default: return row.title ?? t('closing.unassigned');
    }
  };
  const hours = (seconds: number | undefined) => (
    <Box component="span" title={seconds ? formatExactDuration(seconds) : undefined}>{formatHalfHours(seconds ?? 0)}</Box>
  );
  // 24:00 を超える終わり（走っている打刻・日をまたぐ打刻の区切り）は 24:00 まで
  const clock = (minute: number) => formatMinute(Math.min(Math.floor(minute), 24 * 60));

  return (
    <Box data-testid="closing-ledger" sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '8px', overflow: 'hidden' }}>
      <Box sx={{ px: '14px', py: '8px', borderBottom: `1px solid ${ds.borderFaint}`, display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', columnGap: '10px' }}>
        <Box sx={{ fontSize: 14, fontWeight: 700 }}>{t('closing.ledgerTitle')}</Box>
        <Box sx={{ fontSize: 12, color: ds.textMuted }}>
          {t('closing.ledgerNote')}
          <Box component="span" sx={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', bgcolor: AUTO_COLOR, mx: '4px', verticalAlign: 'middle' }} />
          {t('closing.ledgerAutoNote')}
        </Box>
      </Box>
      <Box sx={{ overflowX: 'auto' }}>
        <Box component="table" sx={{ borderCollapse: 'collapse', minWidth: '100%' }}>
          <thead>
            <tr>
              <Box component="th" sx={{ ...cell, ...sticky, textAlign: 'left', minWidth: 150, color: ds.textSub, fontWeight: 700, borderBottom: `2px solid ${ds.text}` }}>
                {t('closing.totalsProject')}
              </Box>
              {ledger.dates.map((d) => (
                <Box component="th" key={d} sx={{ ...cell, ...numeric, fontWeight: 500, color: dayOfWeek(d) === 0 ? ds.dangerText : ds.textSub, borderBottom: `2px solid ${ds.text}` }}>
                  {`${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`}
                  <Box component="span" sx={{ display: 'block', fontSize: 11 }}>{weekdays[dayOfWeek(d)]}</Box>
                </Box>
              ))}
              <Box component="th" sx={{ ...cell, ...numeric, color: ds.textSub, borderBottom: `2px solid ${ds.text}` }}>{t('closing.totalsSum')}</Box>
            </tr>
          </thead>
          <tbody>
            {/* 業務の開始・終了（その日の最初の打刻の始まりと最後の打刻の終わり。休憩は差し引かない） */}
            <tr data-testid="closing-ledger-bounds">
              <Box component="td" sx={{ ...cell, ...sticky, fontSize: 12, color: ds.textSub, borderBottom: `1px dashed ${ds.border}` }}>
                {t('closing.ledgerBounds')}
              </Box>
              {ledger.dates.map((d) => {
                const b = ledger.bounds[d];
                return (
                  <Box component="td" key={d} sx={{ ...cell, ...numeric, lineHeight: 1.25, borderBottom: `1px dashed ${ds.border}` }}>
                    {b ? (
                      <>
                        <Box component="span" sx={{ display: 'block', fontWeight: 700 }}>{clock(b.startMinute)}</Box>
                        <Box component="span" sx={{ display: 'block', fontSize: 12, color: ds.textSub }}>{clock(b.endMinute)}</Box>
                      </>
                    ) : <Box component="span" sx={{ color: ds.textMuted }}>—</Box>}
                  </Box>
                );
              })}
              <Box component="td" sx={{ ...cell, borderBottom: `1px dashed ${ds.border}` }} />
            </tr>
            {/* 休みの行は task #392 でここに入る（日ごとの休みの合計と区間） */}
            {ledger.rows.map((row) => (
              <tr key={row.key}>
                <Box component="td" title={labelOf(row)} sx={{
                  ...cell, ...sticky, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.3,
                  color: row.kind === 'unassigned' ? ds.dangerText : row.kind === 'unclassified' || row.kind === 'outside' ? ds.textSub : ds.text,
                  fontWeight: row.kind === 'unassigned' ? 700 : 400,
                }}>
                  {labelOf(row)}
                  {row.code && (
                    <Box component="span" sx={{ display: 'block', fontSize: 11, color: ds.textMuted, fontFamily: 'ui-monospace, monospace' }}>{row.code}</Box>
                  )}
                </Box>
                {ledger.dates.map((d) => {
                  const seconds = row.byDate[d] ?? 0;
                  const auto = row.autoDates.has(d);
                  return (
                    <Box component="td" key={d} sx={{ ...cell, p: 0 }}>
                      <ButtonBase
                        onClick={() => onOpenCell(d, row)}
                        disabled={seconds === 0 && !auto}
                        aria-label={t('closing.ledgerOpenCell', { date: d, name: labelOf(row) })}
                        sx={{
                          width: '100%', minHeight: 40, px: '10px', justifyContent: 'flex-end', gap: '6px',
                          ...numeric, fontSize: 13, color: seconds === 0 ? ds.textMuted : ds.text,
                          '&:hover': { bgcolor: ds.primaryPale },
                        }}
                        data-testid={`closing-ledger-cell-${row.key}-${d}`}
                      >
                        {hours(seconds)}
                        {auto && (
                          <Box component="span" title={t('timeEntry.autoHint')} sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: AUTO_COLOR, flexShrink: 0 }} />
                        )}
                      </ButtonBase>
                    </Box>
                  );
                })}
                <Box component="td" sx={{ ...cell, ...numeric, fontWeight: 700 }}>{hours(row.total)}</Box>
              </tr>
            ))}
            <tr>
              <Box component="td" sx={{ ...cell, ...sticky, fontWeight: 700, borderTop: `2px solid ${ds.text}`, borderBottom: 0 }}>{t('closing.totalsDay')}</Box>
              {ledger.dates.map((d) => (
                <Box component="td" key={d} sx={{ ...cell, ...numeric, fontWeight: 700, borderTop: `2px solid ${ds.text}`, borderBottom: 0 }}>
                  {hours(ledger.dayTotals[d])}
                </Box>
              ))}
              <Box component="td" sx={{ ...cell, ...numeric, fontWeight: 700, borderTop: `2px solid ${ds.text}`, borderBottom: 0 }}>{hours(ledger.grandTotal)}</Box>
            </tr>
          </tbody>
        </Box>
      </Box>
    </Box>
  );
};

export default LedgerTable;
