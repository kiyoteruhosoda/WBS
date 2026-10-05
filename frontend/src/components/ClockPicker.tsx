import React, { useRef, useState } from 'react';
import { Box, Button, ButtonBase, Dialog, DialogActions, DialogContent } from '@mui/material';
import { useI18n } from '../i18n';
import type { ClockStyle } from '../clock/clockFace';
import { formatClockTime, handOf, hourAtPoint, hourMarks, minuteAtPoint, minuteMarks } from '../clock/clockFace';
import { ds } from '../theme';

interface Props {
  /** 0..1439 の分 */
  value: number;
  style: ClockStyle;
  title: string;
  onCancel: () => void;
  onChoose: (minuteOfDay: number) => void;
}

const SIZE = 260;
const CENTER = SIZE / 2;
const OUTER = 108;
const INNER = 70;
const MARK = 18;

/**
 * 時計の文字盤で時刻を選ぶ（task #287、ADR-0039）。時を押す（なぞる）と分の文字盤へ移り、分は 5 分刻み。
 * 24 時間は外周 0〜11・内周 12〜23、12 時間は 1〜12 と午前／午後。上の時・分を押せばその文字盤へ戻る。
 */
const ClockPicker: React.FC<Props> = ({ value, style, title, onCancel, onChoose }) => {
  const { t } = useI18n();
  const [minuteOfDay, setMinuteOfDay] = useState(value);
  const [view, setView] = useState<'hour' | 'minute'>('hour');
  const dragging = useRef(false);
  const hour = Math.floor(minuteOfDay / 60);
  const minute = minuteOfDay % 60;
  const pm = hour >= 12;
  const labels = { am: t('clock.am'), pm: t('clock.pm') };

  const pointAt = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const scale = SIZE / box.width;
    return { x: (e.clientX - box.left) * scale - CENTER, y: (e.clientY - box.top) * scale - CENTER };
  };
  const pick = (e: React.PointerEvent<SVGSVGElement>) => {
    const { x, y } = pointAt(e);
    if (view === 'hour') setMinuteOfDay(hourAtPoint(x, y, OUTER + MARK, style, pm) * 60 + minute);
    else setMinuteOfDay(hour * 60 + minuteAtPoint(x, y));
  };

  const hand = handOf(view, minuteOfDay, style);
  const handLength = hand.inner ? INNER : OUTER;
  const rad = (hand.angle * Math.PI) / 180;
  const tip = { x: CENTER + Math.sin(rad) * handLength, y: CENTER - Math.cos(rad) * handLength };
  const marks = view === 'hour' ? hourMarks(style) : minuteMarks();
  const selected = view === 'hour' ? hour : minute;
  const shown = formatClockTime(minuteOfDay, style, labels);
  const hourText = style === '24h' ? shown.slice(0, 2) : String(hour % 12 === 0 ? 12 : hour % 12);
  const minuteText = shown.slice(-2);

  const part = (active: boolean) => ({
    fontSize: 40, fontWeight: 700, lineHeight: 1.1, px: '6px', borderRadius: '8px', fontVariantNumeric: 'tabular-nums',
    color: active ? ds.primary : ds.textSub, bgcolor: active ? ds.primaryPale : 'transparent',
  } as const);
  const amPm = (active: boolean) => ({
    fontSize: 14, fontWeight: 700, px: '10px', py: '4px', borderRadius: '6px',
    color: active ? ds.primary : ds.textMuted, bgcolor: active ? ds.primaryPale : 'transparent',
  } as const);

  return (
    <Dialog open onClose={onCancel} maxWidth="xs" data-testid="clock-picker">
      <DialogContent sx={{ pb: 0 }}>
        <Box sx={{ fontSize: 12, color: ds.textSub, mb: '4px' }}>{title}</Box>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2px', mb: '12px' }}>
          <ButtonBase aria-label={t('clock.hour')} onClick={() => setView('hour')} sx={part(view === 'hour')}>{hourText}</ButtonBase>
          <Box sx={{ fontSize: 40, fontWeight: 700, color: ds.textSub }}>:</Box>
          <ButtonBase aria-label={t('clock.minute')} onClick={() => setView('minute')} sx={part(view === 'minute')}>{minuteText}</ButtonBase>
          {style === '12h' && (
            <Box sx={{ display: 'flex', flexDirection: 'column', ml: '8px', gap: '2px' }}>
              <ButtonBase onClick={() => pm && setMinuteOfDay(minuteOfDay - 12 * 60)} sx={amPm(!pm)}>{labels.am}</ButtonBase>
              <ButtonBase onClick={() => !pm && setMinuteOfDay(minuteOfDay + 12 * 60)} sx={amPm(pm)}>{labels.pm}</ButtonBase>
            </Box>
          )}
        </Box>
        <Box
          component="svg"
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="slider"
          aria-label={t(view === 'hour' ? 'clock.hour' : 'clock.minute')}
          aria-valuenow={selected}
          sx={{ display: 'block', width: SIZE, maxWidth: '100%', mx: 'auto', touchAction: 'none', userSelect: 'none', cursor: 'pointer' }}
          onPointerDown={(e: React.PointerEvent<SVGSVGElement>) => {
            dragging.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
            pick(e);
          }}
          onPointerMove={(e: React.PointerEvent<SVGSVGElement>) => { if (dragging.current) pick(e); }}
          onPointerUp={(e: React.PointerEvent<SVGSVGElement>) => {
            if (!dragging.current) return;
            dragging.current = false;
            pick(e);
            // 時を選んだら分へ進む（分を選んだら、そのまま OK を押せる）
            if (view === 'hour') setView('minute');
          }}
        >
          <circle cx={CENTER} cy={CENTER} r={CENTER - 2} fill={ds.track} />
          <line x1={CENTER} y1={CENTER} x2={tip.x} y2={tip.y} stroke={ds.primary} strokeWidth={2} />
          <circle cx={CENTER} cy={CENTER} r={4} fill={ds.primary} />
          <circle cx={tip.x} cy={tip.y} r={MARK} fill={ds.primary} />
          {marks.map((m) => {
            const r = m.inner ? INNER : OUTER;
            const a = (m.angle * Math.PI) / 180;
            const x = CENTER + Math.sin(a) * r;
            const y = CENTER - Math.cos(a) * r;
            const on = m.value === selected;
            return (
              <text
                key={`${m.inner ? 'i' : 'o'}${m.value}`} x={x} y={y} textAnchor="middle" dominantBaseline="central"
                fontSize={m.inner ? 12 : 15} fill={on ? '#fff' : m.inner ? ds.textSub : ds.text} pointerEvents="none"
              >
                {m.label}
              </text>
            );
          })}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>{t('calendar.cancel')}</Button>
        <Button variant="contained" onClick={() => onChoose(minuteOfDay)} sx={{ minHeight: 40 }}>{t('clock.ok')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default ClockPicker;
