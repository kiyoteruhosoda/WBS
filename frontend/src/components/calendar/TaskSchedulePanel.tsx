import React, { useEffect, useRef, useState } from 'react';
import { Box, Button, Collapse, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useI18n } from '../../i18n';
import type { Category, Task } from '../../types';
import { categoryColor } from '../../theme';
import { formatDate } from '../../utils/format';
import { formatHours } from '../../calendar/taskScheduling';
import type { PointerPoint } from '../../calendar/weekGestures';
import { LONG_PRESS_MS, TAP_DISTANCE_PX, autoScrollDelta } from '../../calendar/weekGestures';
import type { WeekSlot } from './weekSlotLocator';
import { locateWeekSlot, weekScrollElement } from './weekSlotLocator';

// 週表示の横のタスクの一覧（task #159）。押せば「このタスクの時間を取る」、引いて時間グリッドへ
// 落とせば予定になる。ポインタイベントだけで追う（`draggable` は使わない）ので、マウスでも指でも同じ道:
// - マウス: 8px 動けば引き始める
// - 指: 300ms の長押しで引き始める（それより先に動けば一覧のスクロール）
// - Esc・2 本目の指で中止。離したら 300ms はクリック（選ぶ）を無視する

const SUPPRESS_CLICK_MS = 300;

interface Props {
  /** 並べるタスク（`schedulableTasks` で絞って並べたもの） */
  tasks: readonly Task[];
  categories: readonly Category[];
  /** 「時間を取る」の最中のタスク */
  selectedTaskId: number | null;
  onSelectTask: (task: Task) => void;
  /** 引いている間、ポインタの下の枠（グリッドの外なら null）。引き終えたら null で呼ぶ */
  onDragOver: (task: Task, slot: WeekSlot | null) => void;
  onDragEnd: () => void;
  /** 時間グリッドへ落とした */
  onDropTask: (task: Task, slot: WeekSlot) => void;
}

interface Press {
  pointerId: number;
  pointerType: string;
  task: Task;
  start: PointerPoint;
  last: PointerPoint;
  dragging: boolean;
  longPressTimer: number | null;
}

const TaskSchedulePanel: React.FC<Props> = ({
  tasks, categories, selectedTaskId, onSelectTask, onDragOver, onDragEnd, onDropTask,
}) => {
  const { t } = useI18n();
  const theme = useTheme();
  const c = theme.palette.calendar;
  const narrow = useMediaQuery(theme.breakpoints.down('md'));
  const [open, setOpen] = useState(false);
  const [dragging, setDragging] = useState<{ task: Task; at: PointerPoint } | null>(null);
  const pressRef = useRef<Press | null>(null);
  const frameRef = useRef<number | null>(null);
  const suppressClickUntil = useRef(0);
  /** 引き始める（effect の中で作る。指の長押しのタイマーから呼ぶ） */
  const beginRef = useRef<((press: Press) => void) | null>(null);
  const latest = useRef({ onDragOver, onDragEnd, onDropTask });
  useEffect(() => {
    latest.current = { onDragOver, onDragEnd, onDropTask };
  });

  const colorOf = (task: Task): string =>
    categoryColor(task.category_id, categories.find((cat) => cat.id === task.category_id)?.color);

  useEffect(() => {
    const stopFrame = () => {
      if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
    const finish = (dropped: boolean) => {
      const press = pressRef.current;
      if (!press) return;
      if (press.longPressTimer != null) window.clearTimeout(press.longPressTimer);
      pressRef.current = null;
      stopFrame();
      if (press.dragging) {
        suppressClickUntil.current = performance.now() + SUPPRESS_CLICK_MS;
        const slot = dropped ? locateWeekSlot(press.last) : null;
        setDragging(null);
        latest.current.onDragEnd();
        if (slot) latest.current.onDropTask(press.task, slot);
      }
    };
    // 端に近い間は時間グリッドを毎フレーム送る（週表示のドラッグと同じ量）。
    const step = () => {
      const press = pressRef.current;
      const el = weekScrollElement();
      if (!press?.dragging || !el) {
        frameRef.current = null;
        return;
      }
      const rect = el.getBoundingClientRect();
      if (press.last.x >= rect.left && press.last.x < rect.right) {
        const delta = autoScrollDelta(press.last.y - rect.top, rect.height);
        if (delta !== 0 && press.last.y > rect.top - 24 && press.last.y < rect.bottom + 24) {
          const before = el.scrollTop;
          el.scrollTop = before + delta;
          if (el.scrollTop !== before) latest.current.onDragOver(press.task, locateWeekSlot(press.last));
        }
      }
      frameRef.current = requestAnimationFrame(step);
    };
    const begin = (press: Press) => {
      if (press.longPressTimer != null) window.clearTimeout(press.longPressTimer);
      press.longPressTimer = null;
      press.dragging = true;
      setDragging({ task: press.task, at: press.last });
      latest.current.onDragOver(press.task, locateWeekSlot(press.last));
      if (frameRef.current == null) frameRef.current = requestAnimationFrame(step);
    };
    const onMove = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId !== press.pointerId) return;
      press.last = { x: e.clientX, y: e.clientY };
      if (press.dragging) {
        setDragging({ task: press.task, at: press.last });
        latest.current.onDragOver(press.task, locateWeekSlot(press.last));
        return;
      }
      const moved = Math.hypot(press.last.x - press.start.x, press.last.y - press.start.y) >= TAP_DISTANCE_PX;
      if (!moved) return;
      // 指で長押しより先に動いた = 一覧のスクロール（ブラウザに任せる）。マウスは引き始め。
      if (press.pointerType === 'touch') finish(false);
      else begin(press);
    };
    const onUp = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId !== press.pointerId) return;
      press.last = { x: e.clientX, y: e.clientY };
      finish(true);
    };
    const onCancel = (e: PointerEvent) => {
      if (pressRef.current && e.pointerId === pressRef.current.pointerId) finish(false);
    };
    const onOtherDown = (e: PointerEvent) => {
      if (pressRef.current && e.pointerId !== pressRef.current.pointerId) finish(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !pressRef.current?.dragging) return;
      e.preventDefault();
      finish(false);
    };
    // 引いている間は指のスクロールを止める（一覧は touch-action で縦のスクロールを許している）。
    const onTouchMove = (e: TouchEvent) => {
      if (pressRef.current?.dragging && e.cancelable) e.preventDefault();
    };
    beginRef.current = begin;
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    window.addEventListener('pointerdown', onOtherDown, true);
    window.addEventListener('keydown', onKey);
    window.addEventListener('touchmove', onTouchMove, { passive: false });
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
      window.removeEventListener('pointerdown', onOtherDown, true);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('touchmove', onTouchMove);
      beginRef.current = null;
      if (pressRef.current?.longPressTimer != null) window.clearTimeout(pressRef.current.longPressTimer);
      pressRef.current = null;
      stopFrame();
    };
  }, []);

  const onItemPointerDown = (e: React.PointerEvent<HTMLElement>, task: Task) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (pressRef.current) return;
    const client = { x: e.clientX, y: e.clientY };
    const press: Press = {
      pointerId: e.pointerId, pointerType: e.pointerType, task, start: client, last: client, dragging: false, longPressTimer: null,
    };
    pressRef.current = press;
    if (e.pointerType === 'mouse') e.preventDefault(); // 文字の選択を始めない
    // 指は長押しで引き始める（それより先に動けば、上の effect がスクロールとして手放す）。
    if (e.pointerType !== 'mouse') {
      press.longPressTimer = window.setTimeout(() => {
        press.longPressTimer = null;
        if (pressRef.current === press && !press.dragging) beginRef.current?.(press);
      }, LONG_PRESS_MS);
    }
  };

  const onItemClick = (task: Task) => {
    if (performance.now() < suppressClickUntil.current) return;
    onSelectTask(task);
  };

  const list = (
    <Box
      component="ul"
      data-testid="task-schedule-list"
      sx={{ listStyle: 'none', m: 0, p: '4px', display: 'flex', flexDirection: 'column', gap: '4px' }}
    >
      {tasks.length === 0 && (
        <Box component="li" sx={{ fontSize: 12, color: c.textSecondary, p: '8px' }}>{t('calendar.taskPanelEmpty')}</Box>
      )}
      {tasks.map((task) => {
        const selected = task.id === selectedTaskId;
        return (
          <Box
            component="li"
            key={task.id}
            data-task-id={task.id}
            role="button"
            tabIndex={0}
            title={t('calendar.taskPanelHint')}
            onPointerDown={(e) => onItemPointerDown(e, task)}
            onClick={() => onItemClick(task)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectTask(task); } }}
            onContextMenu={(e) => e.preventDefault()}
            sx={{
              display: 'flex', alignItems: 'stretch', gap: '6px', p: '6px', borderRadius: '6px', cursor: 'grab',
              border: `1px solid ${selected ? c.blue : c.border}`, bgcolor: selected ? c.surfaceVariant : c.surface,
              opacity: dragging?.task.id === task.id ? 0.5 : 1,
              touchAction: 'pan-y', userSelect: 'none', WebkitUserSelect: 'none', WebkitTouchCallout: 'none',
            }}
          >
            <Box sx={{ width: 4, borderRadius: '2px', bgcolor: colorOf(task), flexShrink: 0 }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box sx={{ fontSize: 13, color: c.textPrimary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {task.title}
              </Box>
              <Box sx={{ fontSize: 11, color: c.textSecondary, display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {task.due_date && <span>{t('calendar.taskPanelDue', { date: formatDate(task.due_date) })}</span>}
                <span>{t('calendar.taskPanelRemaining', { hours: formatHours(task.remaining_hours) })}</span>
                {task.unscheduled_hours != null && (
                  <span>{t('calendar.taskPanelUnscheduled', { hours: formatHours(task.unscheduled_hours) })}</span>
                )}
              </Box>
            </Box>
            <DragIndicatorIcon sx={{ fontSize: 18, color: c.textSecondary, alignSelf: 'center' }} />
          </Box>
        );
      })}
    </Box>
  );

  return (
    <Box
      data-testid="task-schedule-panel"
      sx={{
        display: 'flex', flexDirection: 'column', minHeight: 0, height: narrow ? 'auto' : '100%',
        bgcolor: c.surface, border: `1px solid ${c.border}`, borderRadius: '10px', overflow: 'hidden',
      }}
    >
      {narrow ? (
        <>
          <Button
            onClick={() => setOpen((v) => !v)}
            endIcon={open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            aria-expanded={open}
            sx={{ justifyContent: 'space-between', px: '12px', color: c.textPrimary }}
          >
            {t('calendar.taskPanelTitle', { count: tasks.length })}
          </Button>
          <Collapse in={open}>
            <Box sx={{ maxHeight: 220, overflowY: 'auto' }}>{list}</Box>
          </Collapse>
        </>
      ) : (
        <>
          <Box sx={{ px: '12px', py: '8px', fontSize: 13, fontWeight: 600, color: c.textPrimary, borderBottom: `1px solid ${c.border}` }}>
            {t('calendar.taskPanelTitle', { count: tasks.length })}
            <Box sx={{ fontSize: 11, fontWeight: 400, color: c.textSecondary }}>{t('calendar.taskPanelHint')}</Box>
          </Box>
          <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>{list}</Box>
        </>
      )}
      {/* 引いているタスク（ポインタに付いて動く） */}
      {dragging && (
        <Box
          data-testid="task-drag-chip"
          sx={{
            position: 'fixed', left: dragging.at.x + 8, top: dragging.at.y + 8, zIndex: 1500, pointerEvents: 'none',
            maxWidth: 220, px: '8px', py: '4px', borderRadius: '6px', fontSize: 12, color: c.onColor,
            bgcolor: colorOf(dragging.task), boxShadow: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {dragging.task.title}
        </Box>
      )}
    </Box>
  );
};

export default TaskSchedulePanel;
