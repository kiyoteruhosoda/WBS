import React, { useState } from 'react';
import {
  Alert, Box, Button, Checkbox, Collapse, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, MenuItem, Switch, TextField, ToggleButton, ToggleButtonGroup, useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone';
import EventOutlinedIcon from '@mui/icons-material/EventOutlined';
import TaskAltIcon from '@mui/icons-material/TaskAlt';
import { useI18n } from '../../i18n';
import type { TranslationKey } from '../../i18n/translations';
import type { BusinessCalendar, CalendarEventType, CalendarOccurrence, Task, WeekdayCode } from '../../types';
import type {
  AdjustmentDateType, AdjustmentDirection, AlarmOffsetField, EventForm, EventFormContext, FormError, RecurringScope,
  RepeatType,
} from '../../calendar/eventForm';
import {
  ALARM_OFFSETS, EVENT_COLOR_KEYS, WEEK_INDEXES, WEEKDAY_CODES, endOf, endTimeOptions, isAlarmOn, needsNewTask,
  newTaskPayload, planEventSave, startTimeOptions, withAlarmOffset, withAlarmOn, withEndMinute, withLinkedTask, withRepeat,
  withStartMinute,
} from '../../calendar/eventForm';
import { errorDetailOf, isConflictError } from '../../calendar/calendarRequests';
import { eventColor } from '../../calendar/calendarColors';
import { formatMinute } from '../../calendar/zonedTime';
import { sendCalendarRequests } from '../../api/calendar';
import { createTask } from '../../api/tasks';
import { pickableProjects } from '../../projects/projectScope';
import { useProjectScope } from '../../projects/useProjectScope';
import RecurringScopeDialog from './RecurringScopeDialog';
import TaskPickerField from '../TaskPickerField';

export interface EventEditTarget {
  form: EventForm;
  context: EventFormContext;
}

interface Props {
  target: EventEditTarget;
  /** 閲覧者のタイムゾーン（予定のものと違えば、時刻がどのゾーンのものかを書き添える） */
  viewerTimeZone: string;
  tasks: readonly Task[];
  businessCalendars: readonly BusinessCalendar[];
  onClose: () => void;
  onSaved: () => void;
  /** ほかで予定が変わっていた（409）。呼び手が取り直して知らせる */
  onConflict: () => void;
  /** 削除（範囲を聞くのは呼び手） */
  onDelete?: (occurrence: CalendarOccurrence) => void;
}

const formErrorKeys: Record<FormError, TranslationKey> = {
  titleRequired: 'calendar.errorTitleRequired',
  weekdayRequired: 'calendar.errorWeekdayRequired',
  endDateBeforeStart: 'calendar.errorEndDateBeforeStart',
  taskRequired: 'calendar.errorTaskRequired',
};

const eventTypeKeys: Record<CalendarEventType, TranslationKey> = {
  EVENT: 'calendar.eventTypeEVENT',
  TASK: 'calendar.eventTypeTASK',
};

const repeatKeys: Record<RepeatType, TranslationKey> = {
  NONE: 'calendar.repeatNone',
  WEEKLY: 'calendar.repeatWeekly',
  MONTHLY: 'calendar.repeatMonthly',
  YEARLY: 'calendar.repeatYearly',
};

const alarmOffsetKeys: Record<AlarmOffsetField, TranslationKey> = {
  notify_15_min: 'calendar.alarm15',
  notify_5_min: 'calendar.alarm5',
  notify_1_min: 'calendar.alarm1',
  notify_at_start: 'calendar.alarm0',
};

const intervalUnitKeys: Record<Exclude<RepeatType, 'NONE'>, TranslationKey> = {
  WEEKLY: 'calendar.intervalUnitWeekly',
  MONTHLY: 'calendar.intervalUnitMonthly',
  YEARLY: 'calendar.intervalUnitYearly',
};

const clampInt = (text: string, min: number, max: number, fallback: number): number => {
  const n = Number.parseInt(text, 10);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
};

/** 見出しを押して開く区画（移植元の Expander）。 */
const Section: React.FC<{ title: React.ReactNode; open: boolean; onToggle: () => void; children: React.ReactNode }> = ({
  title, open, onToggle, children,
}) => (
  <Box sx={{ border: 1, borderColor: 'divider', borderRadius: '8px' }}>
    <Box
      component="button"
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      sx={{
        display: 'flex', alignItems: 'center', width: '100%', minHeight: 48, px: '12px', gap: '8px',
        border: 'none', bgcolor: 'transparent', cursor: 'pointer', font: 'inherit', fontSize: 14, color: 'text.primary',
      }}
    >
      <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', gap: '8px', textAlign: 'left' }}>{title}</Box>
      <ExpandMoreIcon sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
    </Box>
    <Collapse in={open}>
      <Box sx={{ px: '12px', pb: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>{children}</Box>
    </Collapse>
  </Box>
);

/**
 * 予定の編集画面（移植元 `EventEditPage` / `EventEditViewModel`）。保存の呼び出しの選び方は
 * `calendar/eventForm.ts` の `planEventSave`。繰り返しの回から開いたら、保存のときに範囲を聞く。
 */
const EventEditDialog: React.FC<Props> = ({
  target, viewerTimeZone, tasks, businessCalendars, onClose, onSaved, onConflict, onDelete,
}) => {
  const { t, weekdays } = useI18n();
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const c = theme.palette.calendar;
  // 「同じ名前のタスク」のプロジェクトは、サイドバーで絞っているプロジェクトを既定にする（タスクの新規作成と同じ）
  const { scope, projects } = useProjectScope();
  const [form, setForm] = useState<EventForm>(() => (
    typeof scope === 'number' && target.form.newTaskProjectId == null ? { ...target.form, newTaskProjectId: scope } : target.form
  ));
  const { context } = target;
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [askScope, setAskScope] = useState(false);
  const [repeatOpen, setRepeatOpen] = useState(target.form.repeat !== 'NONE');
  const [colorOpen, setColorOpen] = useState(target.form.colorKey !== 'DEFAULT');
  const [alarmOpen, setAlarmOpen] = useState(false);

  const isEditing = context.mode === 'edit';
  const deletable = context.mode === 'edit' ? context.occurrence : null;
  const update = (patch: Partial<EventForm>) => setForm((f) => ({ ...f, ...patch }));
  const end = endOf(form);

  const save = async (scope: RecurringScope | null) => {
    setError(null);
    const plan = planEventSave(form, context, scope);
    if (plan.kind === 'invalid') { setError(t(formErrorKeys[plan.error])); return; }
    if (plan.kind === 'needsScope') { setAskScope(true); return; }
    setSaving(true);
    try {
      let { requests } = plan;
      // 分類がタスクでタスクを選んでいなければ、送る直前に同じ名前のタスクを作って結ぶ（ADR-0025）。
      // 作ったタスクは入力に残す（予定の保存に失敗してやり直しても、もう 1 つ作らない）。
      if (needsNewTask(form)) {
        const task = await createTask(newTaskPayload(form));
        const linked = withLinkedTask(form, task.id);
        setForm(linked);
        const again = planEventSave(linked, context, scope);
        if (again.kind !== 'requests') return;
        requests = again.requests;
      }
      await sendCalendarRequests(requests);
      onSaved();
    } catch (e) {
      if (isConflictError(e)) { onConflict(); return; }
      setError(t('calendar.saveFailed', { detail: errorDetailOf(e) ?? '' }));
    } finally {
      setSaving(false);
    }
  };

  const toggleWeekday = (code: WeekdayCode, checked: boolean) =>
    update({ weekdays: checked ? [...form.weekdays.filter((w) => w !== code), code] : form.weekdays.filter((w) => w !== code) });

  const weekIndexLabel = (n: number) => (n === -1 ? t('calendar.nthWeekLast') : t('calendar.nthWeek', { n }));
  const weekdayLabel = (code: WeekdayCode) => weekdays[WEEKDAY_CODES.indexOf(code)];
  const isTask = form.eventType === 'TASK';
  const alarmOn = isAlarmOn(form);
  const alarmSummary = alarmOn && form.alarm
    ? ALARM_OFFSETS.filter((o) => form.alarm?.[o.field]).map((o) => t(alarmOffsetKeys[o.field])).join('・') || t('calendar.alarmNone')
    : t('calendar.alarmNone');
  const endLabel = end.dayOffset === 1 ? ` (${t('calendar.nextDay')})` : end.dayOffset > 1 ? ` (${t('calendar.laterDay', { days: end.dayOffset })})` : '';

  return (
    <>
      <Dialog open onClose={saving ? undefined : onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
        <DialogTitle>{t(isEditing ? 'calendar.editEventTitle' : 'calendar.newEventTitle')}</DialogTitle>
        <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            autoFocus
            label={t('calendar.fieldTitle')}
            value={form.title}
            onChange={(e) => update({ title: e.target.value })}
            slotProps={{ htmlInput: { 'data-testid': 'event-title', maxLength: 500 } }}
          />

          {/* 分類（ADR-0025）。タスクは回ごとに済みを付け、WBS のタスクに結ぶ */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <ToggleButtonGroup
              exclusive
              fullWidth
              size="small"
              color="primary"
              value={form.eventType}
              aria-label={t('calendar.eventType')}
              onChange={(_, value: CalendarEventType | null) => { if (value) update({ eventType: value }); }}
            >
              {(Object.keys(eventTypeKeys) as CalendarEventType[]).map((type) => (
                <ToggleButton key={type} value={type} data-testid={`event-type-${type}`} sx={{ gap: '6px', minHeight: 40 }}>
                  {type === 'TASK' ? <TaskAltIcon sx={{ fontSize: 18 }} /> : <EventOutlinedIcon sx={{ fontSize: 18 }} />}
                  {t(eventTypeKeys[type])}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            {isTask && (
              <>
                <Box sx={{ fontSize: 12, color: 'text.secondary' }}>{t('calendar.eventTypeHint')}</Box>
                <TaskPickerField
                  label={t('calendar.taskToLink')} tasks={tasks} projects={projects} scope={scope}
                  value={form.taskId} onChange={(taskId) => update({ taskId })}
                />
                {form.taskId == null && (
                  <FormControlLabel
                    control={(
                      <Checkbox
                        checked={form.linkNewTask}
                        onChange={(e) => update({ linkNewTask: e.target.checked })}
                        data-testid="event-link-new-task"
                      />
                    )}
                    label={form.title.trim()
                      ? t('calendar.linkNewTaskNamed', { title: form.title.trim() })
                      : t('calendar.linkNewTask')}
                  />
                )}
                {/* 作るタスクのプロジェクト（ADR-0024。作るのは根のタスクなので選べる） */}
                {form.taskId == null && form.linkNewTask && (
                  <TextField
                    select
                    label={t('calendar.newTaskProject')}
                    value={form.newTaskProjectId == null ? '' : String(form.newTaskProjectId)}
                    onChange={(e) => update({ newTaskProjectId: e.target.value === '' ? null : Number(e.target.value) })}
                    slotProps={{
                      inputLabel: { shrink: true },
                      select: {
                        displayEmpty: true,
                        // 選んだ後は道筋で出す（同じ名前の子プロジェクトが別の枝にあっても取り違えない）
                        renderValue: (v) => (v === '' ? t('scope.none') : projects.find((p) => String(p.id) === v)?.path ?? ''),
                      },
                    }}
                    data-testid="event-new-task-project"
                  >
                    <MenuItem value="">{t('scope.none')}</MenuItem>
                    {pickableProjects(projects, form.newTaskProjectId).map(({ project, depth }) => (
                      <MenuItem key={project.id} value={String(project.id)} sx={{ pl: `${16 + depth * 14}px` }}>
                        {project.name}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              </>
            )}
          </Box>
          <TextField label={t('calendar.fieldLocation')} value={form.location} onChange={(e) => update({ location: e.target.value })} />
          <TextField
            label={t('calendar.fieldMemo')}
            value={form.memo}
            onChange={(e) => update({ memo: e.target.value })}
            multiline
            minRows={2}
            maxRows={6}
          />

          {/* 日時 */}
          <Box sx={{ border: 1, borderColor: 'divider', borderRadius: '8px', p: '8px 12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <FormControlLabel
              control={<Switch checked={form.allDay} onChange={(e) => update({ allDay: e.target.checked })} />}
              label={t('calendar.allDay')}
            />
            <TextField
              type="date"
              label={t('calendar.fieldStartDate')}
              value={form.startDate}
              onChange={(e) => { if (e.target.value) update({ startDate: e.target.value }); }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            {!form.allDay && (
              <Box sx={{ display: 'flex', gap: '8px' }}>
                <TextField
                  select
                  fullWidth
                  label={t('calendar.fieldStart')}
                  value={form.startMinute}
                  onChange={(e) => setForm((f) => withStartMinute(f, Number(e.target.value)))}
                  slotProps={{ select: { MenuProps: { slotProps: { paper: { sx: { maxHeight: 320 } } } } } }}
                >
                  {startTimeOptions(form.startMinute).map((m) => <MenuItem key={m} value={m}>{formatMinute(m)}</MenuItem>)}
                </TextField>
                <TextField
                  select
                  fullWidth
                  label={`${t('calendar.fieldEnd')}${endLabel}`}
                  value={end.minute}
                  onChange={(e) => setForm((f) => withEndMinute(f, Number(e.target.value)))}
                  slotProps={{ select: { MenuProps: { slotProps: { paper: { sx: { maxHeight: 320 } } } } } }}
                >
                  {endTimeOptions(end.minute).map((m) => <MenuItem key={m} value={m}>{formatMinute(m)}</MenuItem>)}
                </TextField>
              </Box>
            )}
            {form.timeZone !== viewerTimeZone && (
              <Box sx={{ fontSize: 12, color: 'text.secondary' }}>{t('calendar.timeZoneOfEvent', { zone: form.timeZone })}</Box>
            )}
          </Box>

          {/* 繰り返し */}
          <Section
            title={`${t('calendar.repeat')}: ${t(repeatKeys[form.repeat])}`}
            open={repeatOpen}
            onToggle={() => setRepeatOpen((o) => !o)}
          >
            <TextField
              select
              label={t('calendar.repeat')}
              value={form.repeat}
              onChange={(e) => setForm((f) => withRepeat(f, e.target.value as RepeatType))}
            >
              {(Object.keys(repeatKeys) as RepeatType[]).map((r) => <MenuItem key={r} value={r}>{t(repeatKeys[r])}</MenuItem>)}
            </TextField>

            {form.repeat === 'WEEKLY' && (
              <Box>
                <Box sx={{ fontSize: 12, color: 'text.secondary', mb: '4px' }}>{t('calendar.weekdaysLabel')}</Box>
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>
                  {WEEKDAY_CODES.map((code, i) => (
                    <FormControlLabel
                      key={code}
                      labelPlacement="top"
                      sx={{ m: 0 }}
                      control={<Checkbox checked={form.weekdays.includes(code)} onChange={(e) => toggleWeekday(code, e.target.checked)} />}
                      label={<Box sx={{ fontSize: 11, color: i === 0 ? c.red : i === 6 ? c.blue : 'text.secondary' }}>{weekdays[i]}</Box>}
                    />
                  ))}
                </Box>
              </Box>
            )}

            {form.repeat === 'MONTHLY' && (
              <>
                <TextField
                  select
                  value={form.monthlyKind}
                  onChange={(e) => update({ monthlyKind: e.target.value as EventForm['monthlyKind'] })}
                >
                  <MenuItem value="DAY_OF_MONTH">{t('calendar.monthlyDayOfMonth')}</MenuItem>
                  <MenuItem value="NTH_WEEKDAY">{t('calendar.monthlyNthWeekday')}</MenuItem>
                </TextField>
                {form.monthlyKind === 'DAY_OF_MONTH' ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <TextField
                      type="number"
                      label={t('calendar.dayLabel')}
                      value={form.dayOfMonth}
                      disabled={form.monthlyLastDay}
                      onChange={(e) => update({ dayOfMonth: clampInt(e.target.value, 1, 31, form.dayOfMonth) })}
                      slotProps={{ htmlInput: { min: 1, max: 31 } }}
                      sx={{ width: 120 }}
                    />
                    <FormControlLabel
                      control={<Checkbox checked={form.monthlyLastDay} onChange={(e) => update({ monthlyLastDay: e.target.checked })} />}
                      label={t('calendar.monthlyLastDay')}
                    />
                  </Box>
                ) : (
                  <Box sx={{ display: 'flex', gap: '8px' }}>
                    <TextField select fullWidth value={form.monthlyWeekIndex} onChange={(e) => update({ monthlyWeekIndex: Number(e.target.value) })}>
                      {WEEK_INDEXES.map((n) => <MenuItem key={n} value={n}>{weekIndexLabel(n)}</MenuItem>)}
                    </TextField>
                    <TextField select fullWidth value={form.monthlyWeekday} onChange={(e) => update({ monthlyWeekday: e.target.value as WeekdayCode })}>
                      {WEEKDAY_CODES.map((code) => <MenuItem key={code} value={code}>{weekdayLabel(code)}</MenuItem>)}
                    </TextField>
                  </Box>
                )}
              </>
            )}

            {form.repeat === 'YEARLY' && (
              <>
                <TextField
                  select
                  value={form.yearlyKind}
                  onChange={(e) => update({ yearlyKind: e.target.value as EventForm['yearlyKind'] })}
                >
                  <MenuItem value="DAY_OF_MONTH">{t('calendar.monthlyDayOfMonth')}</MenuItem>
                  <MenuItem value="NTH_WEEKDAY">{t('calendar.monthlyNthWeekday')}</MenuItem>
                </TextField>
                <Box sx={{ display: 'flex', gap: '8px' }}>
                  <TextField
                    type="number"
                    label={t('calendar.monthLabel')}
                    value={form.yearlyMonth}
                    onChange={(e) => update({ yearlyMonth: clampInt(e.target.value, 1, 12, form.yearlyMonth) })}
                    slotProps={{ htmlInput: { min: 1, max: 12 } }}
                    fullWidth
                  />
                  {form.yearlyKind === 'DAY_OF_MONTH' ? (
                    <TextField
                      type="number"
                      label={t('calendar.dayLabel')}
                      value={form.yearlyDay}
                      onChange={(e) => update({ yearlyDay: clampInt(e.target.value, 1, 31, form.yearlyDay) })}
                      slotProps={{ htmlInput: { min: 1, max: 31 } }}
                      fullWidth
                    />
                  ) : (
                    <>
                      <TextField select fullWidth value={form.yearlyWeekIndex} onChange={(e) => update({ yearlyWeekIndex: Number(e.target.value) })}>
                        {WEEK_INDEXES.map((n) => <MenuItem key={n} value={n}>{weekIndexLabel(n)}</MenuItem>)}
                      </TextField>
                      <TextField select fullWidth value={form.yearlyWeekday} onChange={(e) => update({ yearlyWeekday: e.target.value as WeekdayCode })}>
                        {WEEKDAY_CODES.map((code) => <MenuItem key={code} value={code}>{weekdayLabel(code)}</MenuItem>)}
                      </TextField>
                    </>
                  )}
                </Box>
              </>
            )}

            {form.repeat !== 'NONE' && (
              <>
                <FormControlLabel
                  control={<Switch checked={form.useCustomInterval} onChange={(e) => update({ useCustomInterval: e.target.checked })} />}
                  label={t('calendar.useCustomInterval')}
                />
                {form.useCustomInterval && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <TextField
                      type="number"
                      label={t('calendar.interval')}
                      value={form.interval}
                      onChange={(e) => update({ interval: clampInt(e.target.value, 1, 99, form.interval) })}
                      slotProps={{ htmlInput: { min: 1, max: 99 } }}
                      sx={{ width: 120 }}
                    />
                    <Box sx={{ fontSize: 13, color: 'text.secondary' }}>{t(intervalUnitKeys[form.repeat])}</Box>
                  </Box>
                )}
                <FormControlLabel
                  control={<Switch checked={form.hasEndDate} onChange={(e) => update({ hasEndDate: e.target.checked })} />}
                  label={t('calendar.hasEndDate')}
                />
                {form.hasEndDate && (
                  <TextField
                    type="date"
                    label={t('calendar.endDate')}
                    value={form.endDate}
                    onChange={(e) => { if (e.target.value) update({ endDate: e.target.value }); }}
                    slotProps={{ inputLabel: { shrink: true } }}
                  />
                )}

                {/* 営業日調整（移植元 AdjustmentSection） */}
                <FormControlLabel
                  control={<Switch checked={form.useAdjustment} onChange={(e) => update({ useAdjustment: e.target.checked })} />}
                  label={t('calendar.useAdjustment')}
                />
                {form.useAdjustment && (
                  <>
                    <TextField
                      select
                      label={t('calendar.adjustmentDateType')}
                      value={form.adjustmentDateType}
                      onChange={(e) => {
                        const dateType = e.target.value as AdjustmentDateType;
                        // 基準日には「キャンセル」が無い（移植元と同じく「前」へ寄せる）。
                        update({
                          adjustmentDateType: dateType,
                          adjustmentDirection: dateType === 'BASE' && form.adjustmentDirection === 'CANCEL' ? 'BEFORE' : form.adjustmentDirection,
                        });
                      }}
                    >
                      <MenuItem value="SCHEDULED">{t('calendar.adjustmentScheduled')}</MenuItem>
                      <MenuItem value="BASE">{t('calendar.adjustmentBase')}</MenuItem>
                    </TextField>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <TextField
                        select
                        label={t('calendar.adjustmentDirection')}
                        value={form.adjustmentDirection}
                        onChange={(e) => update({ adjustmentDirection: e.target.value as AdjustmentDirection })}
                        sx={{ minWidth: 140 }}
                      >
                        <MenuItem value="BEFORE">{t('calendar.adjustmentBefore')}</MenuItem>
                        <MenuItem value="AFTER">{t('calendar.adjustmentAfter')}</MenuItem>
                        {form.adjustmentDateType === 'SCHEDULED' && <MenuItem value="CANCEL">{t('calendar.adjustmentCancel')}</MenuItem>}
                      </TextField>
                      {form.adjustmentDateType === 'BASE' && (
                        <TextField
                          type="number"
                          label={t('calendar.adjustmentDays')}
                          value={form.adjustmentDays}
                          onChange={(e) => update({ adjustmentDays: clampInt(e.target.value, 0, 31, form.adjustmentDays) })}
                          slotProps={{ htmlInput: { min: 0, max: 31 } }}
                          sx={{ width: 140 }}
                        />
                      )}
                    </Box>
                    <TextField
                      select
                      label={t('calendar.businessCalendar')}
                      value={form.adjustmentCalendarId ?? ''}
                      onChange={(e) => update({ adjustmentCalendarId: e.target.value === '' ? null : Number(e.target.value) })}
                    >
                      <MenuItem value="">{t('calendar.businessCalendarUnset')}</MenuItem>
                      {businessCalendars.map((cal) => <MenuItem key={cal.id} value={cal.id}>{cal.name}</MenuItem>)}
                    </TextField>
                  </>
                )}
              </>
            )}
          </Section>

          {/* 通知（ADR-0021。打刻アプリが端末で出す） */}
          <Section
            title={(
              <>
                <NotificationsNoneIcon sx={{ fontSize: 18 }} />
                {`${t('calendar.alarm')}: ${alarmSummary}`}
              </>
            )}
            open={alarmOpen}
            onToggle={() => setAlarmOpen((o) => !o)}
          >
            <FormControlLabel
              control={<Switch checked={alarmOn} onChange={(e) => setForm((f) => withAlarmOn(f, e.target.checked))} />}
              label={t('calendar.alarmOn')}
            />
            <Box role="group" aria-label={t('calendar.alarm')} sx={{ display: 'flex', flexWrap: 'wrap', columnGap: '8px' }}>
              {ALARM_OFFSETS.map((o) => (
                <FormControlLabel
                  key={o.field}
                  disabled={!alarmOn}
                  control={(
                    <Checkbox
                      checked={form.alarm?.[o.field] ?? true}
                      onChange={(e) => setForm((f) => withAlarmOffset(f, o.field, e.target.checked))}
                    />
                  )}
                  label={t(alarmOffsetKeys[o.field])}
                />
              ))}
            </Box>
            <Box sx={{ fontSize: 12, color: 'text.secondary' }}>
              {t(form.allDay ? 'calendar.alarmAllDayHint' : 'calendar.alarmHint')}
            </Box>
          </Section>

          {/* 色 */}
          <Section
            title={(
              <>
                <Box sx={{ width: 14, height: 14, borderRadius: '50%', bgcolor: eventColor(form.colorKey) }} />
                {`${t('calendar.color')}: ${t(`calendar.color${form.colorKey}` as TranslationKey)}`}
              </>
            )}
            open={colorOpen}
            onToggle={() => setColorOpen((o) => !o)}
          >
            <Box role="radiogroup" aria-label={t('calendar.color')} sx={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {EVENT_COLOR_KEYS.map((key) => {
                const selected = key === form.colorKey;
                const label = t(`calendar.color${key}` as TranslationKey);
                return (
                  <Box
                    key={key}
                    component="button"
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    aria-label={label}
                    title={label}
                    onClick={() => update({ colorKey: key })}
                    sx={{
                      width: 32, height: 32, borderRadius: '50%', cursor: 'pointer', bgcolor: eventColor(key),
                      border: selected ? '3px solid' : '1px solid', borderColor: selected ? 'text.primary' : 'divider',
                      outlineOffset: 2,
                    }}
                  />
                );
              })}
            </Box>
          </Section>

          {/* タスク（WBS のタスクを結ぶ。打刻の既定のタスクになる）。分類がタスクなら上の欄で選ぶ */}
          {!isTask && (
            <TaskPickerField
              label={t('calendar.task')} tasks={tasks} projects={projects} scope={scope}
              value={form.taskId} onChange={(taskId) => update({ taskId })}
            />
          )}
        </DialogContent>
        <DialogActions sx={{ px: '24px', py: '12px' }}>
          {deletable && onDelete && (
            <Button color="error" disabled={saving} onClick={() => onDelete(deletable)} sx={{ mr: 'auto' }}>
              {t('calendar.delete')}
            </Button>
          )}
          <Button onClick={onClose} disabled={saving}>{t('calendar.cancel')}</Button>
          <Button variant="contained" onClick={() => void save(null)} disabled={saving} data-testid="event-save">
            {t('calendar.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <RecurringScopeDialog
        open={askScope}
        purpose="edit"
        onCancel={() => setAskScope(false)}
        onChoose={(scope) => { setAskScope(false); void save(scope); }}
      />
    </>
  );
};

export default EventEditDialog;
