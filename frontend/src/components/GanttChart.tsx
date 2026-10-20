import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Checkbox, IconButton, Popover, TextField, Tooltip } from '@mui/material';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import FlagOutlinedIcon from '@mui/icons-material/FlagOutlined';
import { useTheme } from '@mui/material/styles';
import { getCalendars, getDayOffMarks } from '../api/calendars';
import { CALENDARS_QUERY, DAY_OFF_MARKS_QUERY } from '../calendar/calendarQueries';
import { buildDayOffView, businessDaysBetween } from '../calendar/daysOff';
import { dayColumnBackground } from '../calendar/calendarColors';
import MoreTimeIcon from '@mui/icons-material/MoreTime';
import { scheduleTaskPath } from '../calendar/taskScheduling';
import { useNavigate } from 'react-router-dom';
import type { Task, Category, Milestone } from '../types';
import { forecastGapKey, milestoneForecastIsPartial, taskForecastSpan } from '../forecast/forecastView';
import type { GanttActualSpan } from '../types/actuals';
import { ACTUAL_DAY_COLOR, ACTUAL_STRIP_COLOR, ganttActualLayout } from '../actuals/actualsView';
import { dateRangeParts, displayStatus, formatDate, formatSecondsAsHours, parseDate, todayDate } from '../utils/format';
import type { DisplayStatus } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import CategoryDot from './CategoryDot';
import PriorityChip from './PriorityChip';
import { useSchedulerMove } from '../scheduler/useSchedulerMove';

const DAY_WIDTH = 54;
// 計画の帯・見込みの帯・実績の帯の 3 段が入る高さ（task #556）
const ROW_HEIGHT = 48;
const HEADER_HEIGHT = 56;
const LEFT_WIDTH = 360;
// 表示範囲は今日を基準にクランプする（過去・未来に古いタスクがあっても今日ラインが常に見えるようにする）
const MAX_PAST_DAYS = 30;
const MAX_FUTURE_DAYS = 59;
// 実績の帯（計画の帯の下に細く並べる。task #162）
const PLAN_BAR_HEIGHT = 22;
const PLAN_BAR_HEIGHT_STACKED = 16;
const ACTUAL_STRIP_HEIGHT = 6;
// 見込みの帯（点線の枠と、終わりの日の菱形。ADR-0058）
const FORECAST_BAR_HEIGHT = 9;
const FORECAST_COLOR = ds.primary;
const OVERDUE_COLOR = ds.danger;

const dateOnly = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const addDays = (d: Date, n: number): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const diffDays = (a: Date, b: Date): number => Math.round((dateOnly(a).getTime() - dateOnly(b).getTime()) / 86400000);
/** ローカルの日付を YYYY-MM-DD に（休みの層の API の日付）。 */
const isoDay = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
/** 休みの理由を一度に引ける日数（サーバーの上限 800 日より少し手前） */
const MAX_DAY_OFF_SPAN = 790;
const parse = (s: string | null): Date | null => {
  const d = parseDate(s);
  return d ? dateOnly(d) : null;
};

// ステータス→バー色（トラック / フィル）
const barColors: Record<DisplayStatus, { track: string; fill: string }> = {
  DOING: { track: ds.ganttDoingTrack, fill: ds.primary },
  DONE: { track: ds.successPale2, fill: ds.success },
  TODO: { track: 'transparent', fill: 'transparent' },
  WAITING: { track: ds.warnPale, fill: ds.warnText },
  CANCELLED: { track: ds.track, fill: ds.todoGray },
  LATE: { track: ds.ganttLateTrack, fill: ds.danger },
};

interface Props {
  tasks: Task[];
  categories?: Category[];
  showMeta?: boolean;
  onToggleDone?: (task: Task) => void;
  /** タスクごとの実績の帯（確定した実績の最初〜最後の日と、日ごとの実績）。渡せば計画の帯の下に出す */
  actuals?: Map<number, GanttActualSpan>;
  /** 上に並べるマイルストーン（期限と見込みの日。ADR-0058） */
  milestones?: Milestone[];
  /** 残をその場で直す（渡せば行に「残 Nh」のボタンを出す） */
  onEditRemaining?: (task: Task, hours: number | null) => void;
}

/** 残をその場で直す小さな入れ物。空で保存すると手の値を消し、見積 − 実績 に戻す（ADR-0010） */
const RemainingEditor: React.FC<{
  task: Task;
  anchor: HTMLElement | null;
  onClose: () => void;
  onSave: (hours: number | null) => void;
}> = ({ task, anchor, onClose, onSave }) => {
  const { t } = useI18n();
  const [value, setValue] = useState(task.remaining_hours_entered === null ? '' : String(task.remaining_hours_entered));
  const invalid = value !== '' && !(Number(value) >= 0 && Number(value) <= 9999.99);
  const save = () => { if (!invalid) { onSave(value === '' ? null : Number(value)); onClose(); } };
  return (
    <Popover open={anchor !== null} anchorEl={anchor} onClose={onClose} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
      <Box
        component="form"
        onSubmit={(e) => { e.preventDefault(); save(); }}
        sx={{ p: '12px', display: 'flex', flexDirection: 'column', gap: '8px', width: 240 }}
      >
        <Box sx={{ fontSize: 13, fontWeight: 700 }}>{t('gantt.remainingTitle', { title: task.title })}</Box>
        <TextField
          autoFocus size="small" type="number" label={t('taskEdit.remainingHours')} value={value} error={invalid}
          placeholder={task.remaining_hours === null ? '' : String(task.remaining_hours)}
          slotProps={{ htmlInput: { min: 0, step: 0.5 } }}
          onChange={(e) => setValue(e.target.value)}
        />
        <Box sx={{ fontSize: 12, color: ds.textMuted }}>{t('gantt.remainingHint')}</Box>
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <Button size="small" onClick={onClose} sx={{ color: ds.textSub }}>{t('gantt.cancel')}</Button>
          <Button size="small" variant="contained" type="submit" disabled={invalid}>{t('gantt.save')}</Button>
        </Box>
      </Box>
    </Popover>
  );
};

const GanttChart: React.FC<Props> = ({
  tasks, categories, showMeta = true, onToggleDone, actuals, milestones = [], onEditRemaining,
}) => {
  const navigate = useNavigate();
  const { t, weekdays } = useI18n();
  // 行の中では `t` をタスクの変数に使っているので、訳は別名で持つ
  const tr = t;
  const today = todayDate();
  // 予定を Scheduler へ移した後は「時間を取る」を出さない（task #535 / ADR-0054）
  const schedulerMove = useSchedulerMove();
  const [remainingOf, setRemainingOf] = useState<{ task: Task; anchor: HTMLElement } | null>(null);
  // 期限か見込みのあるマイルストーンだけ（上に並べる）
  const milestoneRows = useMemo(
    () => milestones
      .filter((m) => m.due_date || m.forecast_finish)
      .sort((a, b) => (a.due_date ?? a.forecast_finish ?? '').localeCompare(b.due_date ?? b.forecast_finish ?? '')),
    [milestones],
  );

  const { rangeStart, days } = useMemo(() => {
    let min = addDays(today, -3);
    let max = addDays(today, 10);
    for (const t of tasks) {
      const s = parse(t.start_date) ?? parse(t.due_date);
      const e = parse(t.due_date) ?? parse(t.start_date);
      if (s && s < min) min = s;
      if (e && e > max) max = e;
      // 見込みの帯も入るように（ADR-0058）
      const fs = parse(t.forecast_start ?? null);
      const fe = parse(t.forecast_finish ?? null);
      if (fs && fs < min) min = fs;
      if (fe && fe > max) max = fe;
    }
    for (const m of milestoneRows) {
      for (const d of [parse(m.due_date), parse(m.forecast_finish ?? null)]) {
        if (d && d < min) min = d;
        if (d && d > max) max = d;
      }
    }
    min = addDays(min, -1);
    max = addDays(max, 1);
    // 今日を含む一定幅にクランプ（範囲外にかかるバーは端で切って表示する）
    const clampMin = addDays(today, -MAX_PAST_DAYS);
    const clampMax = addDays(today, MAX_FUTURE_DAYS);
    if (min < clampMin) min = clampMin;
    if (max > clampMax) max = clampMax;
    const n = diffDays(max, min) + 1;
    return { rangeStart: min, days: Array.from({ length: n }, (_, i) => addDays(min, i)) };
  }, [tasks, milestoneRows, today]);

  const todayIdx = diffDays(today, rangeStart);
  const timelineWidth = days.length * DAY_WIDTH;

  // 休みの 4 層（ADR-0029）: 表示中の層で日の列を塗り、タスクの期間の営業日の数を出す（数は表示に関係しない）。
  // 範囲の外にはみ出すタスクの期間も数えるので、引く期間はタスクの期間まで広げる。
  const calendarPalette = useTheme().palette.calendar;
  const markRange = useMemo(() => {
    let from = days[0];
    let to = days[days.length - 1];
    for (const t of tasks) {
      const s = parse(t.start_date) ?? parse(t.due_date);
      const e = parse(t.due_date) ?? parse(t.start_date);
      if (s && s < from) from = s;
      if (e && e > to) to = e;
    }
    if (diffDays(to, from) > MAX_DAY_OFF_SPAN) return { from: isoDay(days[0]), to: isoDay(days[days.length - 1]) };
    return { from: isoDay(from), to: isoDay(to) };
  }, [days, tasks]);
  const { data: marks } = useQuery({
    queryKey: [DAY_OFF_MARKS_QUERY, markRange.from, markRange.to],
    queryFn: () => getDayOffMarks(markRange),
  });
  const { data: calendars } = useQuery({ queryKey: [CALENDARS_QUERY], queryFn: getCalendars });
  const dayOffView = useMemo(() => buildDayOffView(marks ?? [], calendars), [marks, calendars]);
  const holidayByDate = useMemo(() => new Map(dayOffView.holidays.map((h) => [h.date, h])), [dayOffView]);
  const columnBackground = (d: Date): string => {
    const key = isoDay(d);
    return dayColumnBackground(
      calendarPalette, d.getDay(), holidayByDate.get(key),
      dayOffView.nonWorkdays ? dayOffView.nonWorkdays.has(key) : null,
    );
  };
  const businessDaysOf = (s: Date, e: Date): number | null => {
    if (!marks || isoDay(s) < markRange.from || isoDay(e) > markRange.to) return null;
    return businessDaysBetween(isoDay(s), isoDay(e), dayOffView.nonBusinessDays);
  };

  // 初期表示で今日が見えるようにスクロールする（今日を左から1/3の位置に置く）
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || todayIdx < 0) return;
    const target = todayIdx * DAY_WIDTH + DAY_WIDTH / 2 - el.clientWidth / 3;
    el.scrollLeft = Math.max(0, target);
    // 表示範囲が変わったときだけ位置を合わせ直す
  }, [todayIdx, timelineWidth]);

  return (
    <Box sx={{ display: 'flex', border: `1px solid ${ds.border}`, borderRadius: '10px', bgcolor: ds.paper, overflow: 'hidden' }}>
      {/* 左: タスク名パネル */}
      <Box sx={{ width: { xs: 220, md: LEFT_WIDTH }, flexShrink: 0, borderRight: `1px solid ${ds.border}` }}>
        <Box sx={{
          height: HEADER_HEIGHT, display: 'flex', alignItems: 'center', px: '14px',
          bgcolor: '#F7F7F8', borderBottom: `1px solid ${ds.border}`,
          fontSize: 13, fontWeight: 700, color: ds.textSub,
        }}>
          {t('gantt.taskName')}
        </Box>
        {milestoneRows.map((m) => (
          <Box key={`m${m.id}`} data-testid="gantt-milestone-row" sx={{
            height: ROW_HEIGHT, display: 'flex', alignItems: 'center', gap: '8px', px: '12px',
            borderBottom: '1px solid #ECECEE', bgcolor: '#FAFAFB',
          }}>
            <FlagOutlinedIcon sx={{ fontSize: 18, color: ds.textSub }} aria-hidden />
            <Box
              onClick={() => navigate('/milestones')}
              sx={{
                flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: ds.text, cursor: 'pointer',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', '&:hover': { color: ds.primary },
              }}
            >
              {m.name}
            </Box>
            {(m.forecast_overdue_days ?? 0) > 0 && (
              <Tooltip title={tr('gantt.overdueTip', { days: m.forecast_overdue_days ?? 0 })}>
                <WarningAmberIcon
                  titleAccess={tr('gantt.overdueTip', { days: m.forecast_overdue_days ?? 0 })}
                  sx={{ fontSize: 18, color: OVERDUE_COLOR }}
                />
              </Tooltip>
            )}
          </Box>
        ))}
        {tasks.map((t) => (
          <Box key={t.id} sx={{
            height: ROW_HEIGHT, display: 'flex', alignItems: 'center', gap: '8px', px: '8px',
            borderBottom: '1px solid #ECECEE', '&:last-child': { borderBottom: 'none' },
          }}>
            <Checkbox
              size="small"
              checked={t.status === 'DONE'}
              onChange={() => onToggleDone?.(t)}
              sx={{ p: '4px', color: ds.todoGray, '&.Mui-checked': { color: ds.success } }}
            />
            <CategoryDot categoryId={t.category_id} categories={categories} size={7} />
            <Box
              onClick={() => navigate(`/tasks/${t.id}`)}
              sx={{
                flex: 1, minWidth: 0, fontSize: 13, color: ds.text, cursor: 'pointer',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                textDecoration: t.status === 'DONE' ? 'line-through' : 'none',
                '&:hover': { color: ds.primary },
              }}
            >
              {t.title}
            </Box>
            {(t.forecast_overdue_days ?? 0) > 0 && (
              <Tooltip title={tr('gantt.overdueTip', { days: t.forecast_overdue_days ?? 0 })}>
                <WarningAmberIcon
                  titleAccess={tr('gantt.overdueTip', { days: t.forecast_overdue_days ?? 0 })}
                  sx={{ fontSize: 18, color: OVERDUE_COLOR }}
                />
              </Tooltip>
            )}
            {onEditRemaining && !t.has_subtasks && t.status !== 'DONE' && t.status !== 'CANCELLED' && (
              <Tooltip title={tr('gantt.remainingEdit')}>
                <Button
                  size="small" variant="text"
                  aria-label={`${tr('gantt.remainingEdit')}: ${t.title}`}
                  onClick={(e) => setRemainingOf({ task: t, anchor: e.currentTarget })}
                  sx={{ minWidth: 0, px: '6px', py: 0, fontSize: 11, color: ds.textSub, whiteSpace: 'nowrap', display: { xs: 'none', sm: 'inline-flex' } }}
                >
                  {t.remaining_hours === null ? tr('gantt.remainingUnknown') : tr('gantt.remainingShort', { hours: t.remaining_hours })}
                </Button>
              </Tooltip>
            )}
            {showMeta && <PriorityChip priority={t.priority} />}
            {t.status !== 'DONE' && t.status !== 'CANCELLED' && !schedulerMove.moved && (
              <Tooltip title={tr('task.scheduleTime')}>
                <IconButton
                  size="small"
                  aria-label={tr('task.scheduleTime')}
                  onClick={() => navigate(scheduleTaskPath(t.id))}
                  sx={{ p: '4px', color: ds.textSub }}
                >
                  <MoreTimeIcon sx={{ fontSize: 18 }} />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        ))}
      </Box>

      {/* 右: タイムライン */}
      <Box ref={scrollRef} sx={{ flex: 1, minWidth: 0, overflowX: 'auto' }}>
        <Box sx={{ position: 'relative', width: timelineWidth }}>
          {/* ヘッダ */}
          <Box sx={{ display: 'flex', height: HEADER_HEIGHT, bgcolor: '#F7F7F8', borderBottom: `1px solid ${ds.border}` }}>
            {days.map((d, i) => {
              const dow = d.getDay();
              const color = dow === 0 ? ds.dangerText : dow === 6 ? ds.primary : ds.textSub;
              return (
                <Box key={i} title={holidayByDate.get(isoDay(d))?.name ?? undefined} sx={{
                  width: DAY_WIDTH, flexShrink: 0, textAlign: 'center', pt: '9px',
                  borderLeft: i === 0 ? 'none' : '1px solid #ECECEE',
                  bgcolor: columnBackground(d),
                  borderBottom: holidayByDate.get(isoDay(d))?.color ? `3px solid ${holidayByDate.get(isoDay(d))?.color}` : 'none',
                }}>
                  <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text }}>{d.getMonth() + 1}/{d.getDate()}</Box>
                  <Box sx={{ fontSize: 11, color }}>{weekdays[dow]}</Box>
                </Box>
              );
            })}
          </Box>

          {/* 行グリッド + バー */}
          <Box sx={{ position: 'relative' }}>
            {/* 縦グリッド・土日シェード */}
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', pointerEvents: 'none' }}>
              {days.map((d, i) => (
                <Box key={i} sx={{
                  width: DAY_WIDTH, flexShrink: 0,
                  borderLeft: i === 0 ? 'none' : '1px solid #F2F2F3',
                  bgcolor: columnBackground(d),
                }} />
              ))}
            </Box>

            {milestoneRows.map((m) => {
              const due = parse(m.due_date);
              const finish = parse(m.forecast_finish ?? null);
              const overdue = (m.forecast_overdue_days ?? 0) > 0;
              const marker = (d: Date, kind: 'due' | 'forecast') => {
                const idx = diffDays(d, rangeStart);
                if (idx < 0 || idx > days.length - 1) return null;
                const color = kind === 'due' ? ds.text : overdue ? OVERDUE_COLOR : FORECAST_COLOR;
                return (
                  <Box
                    key={kind}
                    aria-hidden
                    sx={{
                      position: 'absolute', left: idx * DAY_WIDTH + DAY_WIDTH / 2 - 7, top: ROW_HEIGHT / 2 - 7,
                      width: 14, height: 14, transform: 'rotate(45deg)',
                      bgcolor: kind === 'due' ? color : ds.paper,
                      border: kind === 'due' ? 'none' : `2px dashed ${color}`,
                    }}
                  />
                );
              };
              const labelDay = finish ?? due;
              const labelIdx = labelDay ? Math.min(days.length - 1, Math.max(0, diffDays(labelDay, rangeStart))) : null;
              const forecastText = m.forecast_finish
                ? tr(milestoneForecastIsPartial(m) ? 'gantt.milestoneForecastPartial' : 'gantt.milestoneForecast', {
                  date: formatDate(m.forecast_finish), count: m.forecast_unforecast_count ?? 0,
                })
                : tr('gantt.milestoneNoForecast');
              return (
                <Box key={`m${m.id}`} data-testid="gantt-milestone-timeline" sx={{
                  position: 'relative', height: ROW_HEIGHT, borderBottom: '1px solid #ECECEE',
                }}>
                  {due && marker(due, 'due')}
                  {finish && marker(finish, 'forecast')}
                  {labelIdx !== null && (
                    <Box sx={{
                      position: 'absolute', left: labelIdx * DAY_WIDTH + DAY_WIDTH / 2 + 12, top: 0, height: ROW_HEIGHT,
                      display: 'flex', alignItems: 'center', gap: '6px', fontSize: 11, whiteSpace: 'nowrap', pointerEvents: 'none',
                      color: overdue ? ds.dangerText : ds.textSub, fontWeight: overdue ? 700 : 400,
                    }}>
                      {forecastText}
                      {overdue && <span>{tr('gantt.overdueLabel', { days: m.forecast_overdue_days ?? 0 })}</span>}
                    </Box>
                  )}
                </Box>
              );
            })}

            {tasks.map((t) => {
              const st = displayStatus(t);
              const s = parse(t.start_date) ?? parse(t.due_date);
              const e = parse(t.due_date) ?? parse(t.start_date);
              let bar: React.ReactNode = null;
              const actualLayout = ganttActualLayout(actuals?.get(t.id), rangeStart, days.length);
              const hasActual = actualLayout.strip !== null;
              const forecastSpan = taskForecastSpan(t);
              // 実績か見込みの帯があれば計画の帯を細くして上へ寄せ、下に 見込み → 実績 の順に置く
              const gapKey = forecastSpan === null ? forecastGapKey(t.forecast_gap) : null;
              // 見込みの出ない理由も見込みの段に書く（行からはみ出さないよう計画の帯を上へ寄せる）
              const stacked = hasActual || forecastSpan !== null || gapKey !== null;
              const planHeight = stacked ? PLAN_BAR_HEIGHT_STACKED : PLAN_BAR_HEIGHT;
              const planTop = stacked ? 4 : (ROW_HEIGHT - PLAN_BAR_HEIGHT) / 2;
              const forecastTop = planTop + planHeight + 4;
              const actualTop = forecastSpan !== null ? forecastTop + FORECAST_BAR_HEIGHT + 5 : planTop + planHeight + 4;
              const span = actuals?.get(t.id);
              const actualStrip = actualLayout.strip && span ? (
                <Box
                  aria-label={tr('gantt.actualTip', dateRangeParts(span.first_date, span.last_date))}
                  title={tr('gantt.actualTip', dateRangeParts(span.first_date, span.last_date))}
                  sx={{
                    position: 'absolute',
                    left: actualLayout.strip.startIdx * DAY_WIDTH + 3,
                    width: (actualLayout.strip.endIdx - actualLayout.strip.startIdx + 1) * DAY_WIDTH - 6,
                    top: actualTop, height: ACTUAL_STRIP_HEIGHT,
                    borderRadius: '4px', bgcolor: ACTUAL_STRIP_COLOR,
                  }}
                />
              ) : null;
              const actualCells = actualLayout.cells.map((c) => {
                const day = days[c.idx];
                const label = tr('gantt.actualDayTip', {
                  date: formatDate(day), hours: formatSecondsAsHours(c.seconds),
                });
                return (
                  <Box
                    key={c.idx}
                    title={label}
                    sx={{
                      position: 'absolute', left: c.idx * DAY_WIDTH + 8, width: DAY_WIDTH - 16,
                      top: actualTop, height: ACTUAL_STRIP_HEIGHT,
                      borderRadius: '4px', bgcolor: ACTUAL_DAY_COLOR,
                    }}
                  />
                );
              });
              if (s && e) {
                const startIdx = Math.max(0, diffDays(s, rangeStart));
                const endIdx = Math.min(days.length - 1, diffDays(e, rangeStart));
                if (endIdx >= 0 && startIdx <= days.length - 1 && endIdx >= startIdx) {
                  const left = startIdx * DAY_WIDTH + 3;
                  const width = (endIdx - startIdx + 1) * DAY_WIDTH - 6;
                  const colors = barColors[st];
                  const fillPct = st === 'DONE' ? 100 : Math.max(0, Math.min(100, t.progress_percent ?? 0));
                  const businessDays = businessDaysOf(s, e);
                  const businessLabel = businessDays != null ? tr('gantt.businessDays', { count: businessDays }) : null;
                  bar = (
                    <>
                    {businessLabel && (
                      <Box
                        data-testid="gantt-business-days"
                        sx={{
                          position: 'absolute', left: left + width + 6, top: planTop, height: planHeight,
                          display: 'flex', alignItems: 'center', fontSize: 11, color: ds.textSub, whiteSpace: 'nowrap',
                          pointerEvents: 'none',
                        }}
                      >
                        {businessLabel}
                      </Box>
                    )}
                    <Box
                      onClick={() => navigate(`/tasks/${t.id}`)}
                      sx={{
                        position: 'absolute', left, width, top: planTop, height: planHeight,
                        borderRadius: '6px', cursor: 'pointer', overflow: 'hidden',
                        bgcolor: colors.track,
                        border: st === 'TODO' ? `1.5px dashed ${ds.todoGray}` : 'none',
                      }}
                      title={`${t.title}（${t.progress_percent === null ? '—' : `${t.progress_percent}%`}${businessLabel ? `・${businessLabel}` : ''}）`}
                    >
                      {st !== 'TODO' && (
                        <Box sx={{ width: `${fillPct}%`, height: '100%', borderRadius: '6px', bgcolor: colors.fill }} />
                      )}
                    </Box>
                    </>
                  );
                }
              }
              // 見込みの帯（点線の枠）と終わりの菱形。期限を越えるなら赤に加え、期限の日に縦の線と「⚠ 期限 +N 日」（ADR-0058）
              let forecast: React.ReactNode = null;
              if (forecastSpan) {
                const fe = parse(forecastSpan.finish) ?? today;
                const fs = parse(forecastSpan.start) ?? fe;
                const overdue = forecastSpan.overdueDays > 0;
                const color = overdue ? OVERDUE_COLOR : FORECAST_COLOR;
                const startIdx = Math.max(0, diffDays(fs, rangeStart));
                const rawEndIdx = diffDays(fe, rangeStart);
                const endIdx = Math.min(days.length - 1, rawEndIdx);
                const tip = tr(overdue ? 'gantt.forecastOverdueTip' : 'gantt.forecastTip', {
                  ...dateRangeParts(forecastSpan.start, forecastSpan.finish), days: forecastSpan.overdueDays,
                });
                const due = parse(t.due_date);
                const dueIdx = due ? diffDays(due, rangeStart) : -1;
                if (endIdx >= 0 && startIdx <= days.length - 1 && endIdx >= startIdx) {
                  const left = startIdx * DAY_WIDTH + 3;
                  const width = (endIdx - startIdx + 1) * DAY_WIDTH - 6;
                  forecast = (
                    <>
                      <Box
                        data-testid="gantt-forecast"
                        data-overdue={overdue ? 'true' : 'false'}
                        role="img" aria-label={tip} title={tip}
                        sx={{
                          position: 'absolute', left, width, top: forecastTop, height: FORECAST_BAR_HEIGHT,
                          borderRadius: '3px', border: `1.5px dashed ${color}`, boxSizing: 'border-box',
                          bgcolor: overdue ? ds.dangerPale : ds.primaryPale,
                        }}
                      />
                      {rawEndIdx === endIdx && (
                        <Box aria-hidden sx={{
                          position: 'absolute', left: endIdx * DAY_WIDTH + DAY_WIDTH - 10, top: forecastTop - 1,
                          width: 10, height: 10, transform: 'rotate(45deg)', bgcolor: color,
                        }} />
                      )}
                      {overdue && dueIdx >= 0 && dueIdx < days.length && (
                        <Box aria-hidden sx={{
                          position: 'absolute', left: dueIdx * DAY_WIDTH + DAY_WIDTH - 2, top: 2, bottom: 2,
                          borderLeft: `2px dashed ${OVERDUE_COLOR}`,
                        }} />
                      )}
                      <Box
                        data-testid="gantt-forecast-label"
                        sx={{
                          position: 'absolute', left: left + width + 8, top: forecastTop - 4, height: FORECAST_BAR_HEIGHT + 8,
                          display: 'flex', alignItems: 'center', gap: '6px', fontSize: 11, whiteSpace: 'nowrap', pointerEvents: 'none',
                          color: overdue ? ds.dangerText : ds.textSub, fontWeight: overdue ? 700 : 400,
                        }}
                      >
                        {tr('gantt.forecastShort', { date: formatDate(forecastSpan.finish) })}
                        {overdue && <span>{tr('gantt.overdueLabel', { days: forecastSpan.overdueDays })}</span>}
                      </Box>
                    </>
                  );
                }
              } else if (gapKey && todayIdx >= 0 && todayIdx < days.length) {
                forecast = (
                  <Box
                    data-testid="gantt-forecast-gap"
                    sx={{
                      position: 'absolute', left: todayIdx * DAY_WIDTH + DAY_WIDTH / 2 + 6, top: forecastTop - 3, lineHeight: '15px',
                      fontSize: 11, color: ds.textMuted, whiteSpace: 'nowrap', pointerEvents: 'none',
                    }}
                  >
                    {tr('gantt.noForecast', { reason: tr(gapKey) })}
                  </Box>
                );
              }
              return (
                <Box key={t.id} sx={{
                  position: 'relative', height: ROW_HEIGHT,
                  borderBottom: '1px solid #ECECEE', '&:last-child': { borderBottom: 'none' },
                }}>
                  {bar}
                  {forecast}
                  {actualStrip}
                  {actualCells}
                </Box>
              );
            })}

            {/* 今日ライン */}
            {todayIdx >= 0 && todayIdx < days.length && (
              <Box sx={{
                position: 'absolute', top: 0, bottom: 0, pointerEvents: 'none',
                left: todayIdx * DAY_WIDTH + DAY_WIDTH / 2, width: 0, borderLeft: `2px solid ${ds.danger}`,
              }} />
            )}
          </Box>

          {/* 今日ラベル（ヘッダ上） */}
          {todayIdx >= 0 && todayIdx < days.length && (
            <Box sx={{
              position: 'absolute', top: HEADER_HEIGHT - 16,
              left: todayIdx * DAY_WIDTH + DAY_WIDTH / 2, transform: 'translateX(-50%)',
              bgcolor: ds.danger, color: '#fff', fontSize: 10, fontWeight: 700,
              px: '6px', py: '1px', borderRadius: '4px', pointerEvents: 'none',
            }}>
              {t('gantt.today')}
            </Box>
          )}
        </Box>
      </Box>
      {remainingOf && onEditRemaining && (
        <RemainingEditor
          task={remainingOf.task} anchor={remainingOf.anchor} onClose={() => setRemainingOf(null)}
          onSave={(hours) => onEditRemaining(remainingOf.task, hours)}
        />
      )}
    </Box>
  );
};

export default GanttChart;
