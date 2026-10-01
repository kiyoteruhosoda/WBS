import type React from 'react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CalendarOccurrence } from '../../types';
import type { WeekEventBlock } from '../../calendar/weekLayout';
import type { GrabbedSegment, OccurrenceTiming, PointerPoint } from '../../calendar/weekGestures';
import {
  LONG_PRESS_MS, autoScrollDelta, createRange, dayIndexAt, decideGesture, moveTiming, resizeTiming, sameTiming,
} from '../../calendar/weekGestures';
import { fromZonedPoint, toZonedPoint } from '../../calendar/zonedTime';
import type { CalendarInteractions, OccurrenceReschedule, OccurrenceSchedule } from './calendarInteractions';

// 週表示のドラッグ（移植元 `WeekCalendarView` の PointerPressed / Manipulation* と Esc の取り消し）。
// ポインタイベントだけで追う（`draggable` は使わない）ので、マウスでも指でも同じ道を通る。
// - 予定: 8px 動けば移動、上端・下端のつかみを縦に動かせば伸ばし縮め
// - 空き枠: マウスは 8px 動けば範囲作り、指は 300ms の長押しで範囲作り（それより先に動けばスクロール）
// - 離すまで意図は出さない。離したら 300ms はクリックを無視する（移植元 `_suppressTapUntilUtc`）

/** 日の列（時間グリッドの中）に WeekView が付ける印。ポインタの位置から日と分を引くのに使う。 */
const DAY_COLUMN_ATTRIBUTE = 'data-day-column';

const SUPPRESS_CLICK_MS = 300;

/** 描いている途中の形（ゴースト）。 */
export interface WeekDragGhost {
  kind: 'create' | 'move' | 'resize';
  /** 動かしている回。作るときは null */
  occurrenceId: string | null;
  timing: OccurrenceTiming;
  /** つかんだ予定の横の位置（ゴーストを同じ幅で描く）。作るときは列いっぱい */
  leftRatio: number;
  widthRatio: number;
}

type Phase = 'pressed' | 'create' | 'move' | 'resize';

interface Press {
  pointerId: number;
  pointerType: string;
  phase: Phase;
  startClient: PointerPoint;
  lastClient: PointerPoint;
  startTime: number;
  /** 押した日と、その日の 0:00 からの位置（px = 分、丸める前） */
  startDate: string;
  startY: number;
  block: WeekEventBlock | null;
  edge: 'top' | 'bottom' | null;
  origin: OccurrenceTiming | null;
  longPressTimer: number | null;
}

interface Options extends Pick<CalendarInteractions, 'onCreateRange' | 'onRescheduleOccurrence'> {
  dates: readonly string[];
  timeZone: string;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}

const originOf = (occurrence: CalendarOccurrence, timeZone: string): OccurrenceTiming => {
  const p = toZonedPoint(Date.parse(occurrence.start), timeZone);
  return { date: p.date, startMinute: p.minute, durationMinutes: occurrence.duration_minutes };
};

export const useWeekDrag = ({ dates, timeZone, scrollRef, onCreateRange, onRescheduleOccurrence }: Options) => {
  const [ghost, setGhost] = useState<WeekDragGhost | null>(null);
  const pressRef = useRef<Press | null>(null);
  const ghostRef = useRef<WeekDragGhost | null>(null);
  const frameRef = useRef<number | null>(null);
  const suppressClickUntil = useRef(0);
  const latest = useRef({ dates, timeZone, onCreateRange, onRescheduleOccurrence });
  useLayoutEffect(() => {
    latest.current = { dates, timeZone, onCreateRange, onRescheduleOccurrence };
  });

  const showGhost = useCallback((next: WeekDragGhost | null) => {
    const current = ghostRef.current;
    if (current === next) return;
    if (current && next && current.kind === next.kind && current.occurrenceId === next.occurrenceId
      && sameTiming(current.timing, next.timing)) return;
    ghostRef.current = next;
    setGhost(next);
  }, []);

  /** ポインタの位置 → 日と、その日の 0:00 からの位置（px = 分）。列が見つからなければ null。 */
  const locate = useCallback((client: PointerPoint): { date: string; y: number } | null => {
    const columns = scrollRef.current?.querySelectorAll<HTMLElement>(`[${DAY_COLUMN_ATTRIBUTE}]`);
    if (!columns || columns.length === 0) return null;
    const first = columns[0].getBoundingClientRect();
    const last = columns[columns.length - 1].getBoundingClientRect();
    const width = (last.right - first.left) / columns.length;
    const index = dayIndexAt(client.x - first.left, width, columns.length);
    const date = columns[index].getAttribute(DAY_COLUMN_ATTRIBUTE) ?? latest.current.dates[index];
    return { date, y: client.y - first.top };
  }, [scrollRef]);

  /** いまのポインタの位置から、ゴーストの形を作り直す。 */
  const preview = useCallback((): WeekDragGhost | null => {
    const press = pressRef.current;
    if (!press || press.phase === 'pressed') return null;
    const at = locate(press.lastClient);
    if (!at) return ghostRef.current;
    const delta = at.y - press.startY;
    if (press.phase === 'create') {
      const range = createRange(press.startY, at.y);
      return {
        kind: 'create', occurrenceId: null, leftRatio: 0, widthRatio: 1,
        timing: { date: press.startDate, startMinute: range.startMinute, durationMinutes: range.endMinute - range.startMinute },
      };
    }
    const block = press.block;
    const origin = press.origin;
    if (!block || !origin) return null;
    const grabbed: GrabbedSegment = { date: block.segment.date, startMinute: block.top, endMinute: block.top + block.height };
    const timing = press.phase === 'move'
      ? moveTiming(origin, grabbed, at.date, delta)
      : resizeTiming(origin, grabbed, press.edge ?? 'bottom', delta);
    return {
      kind: press.phase, occurrenceId: block.segment.occurrence.id, timing,
      leftRatio: block.leftRatio, widthRatio: block.widthRatio,
    };
  }, [locate]);

  const finish = useCallback(() => {
    const press = pressRef.current;
    if (press?.longPressTimer != null) window.clearTimeout(press.longPressTimer);
    pressRef.current = null;
    if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    showGhost(null);
  }, [showGhost]);

  // 端に近い間は毎フレーム送る（1 回 2〜24px）。送ったらゴーストも追わせる。
  const startAutoScroll = useCallback(() => {
    if (frameRef.current != null) return;
    function step(): void {
      const press = pressRef.current;
      const el = scrollRef.current;
      if (!press || press.phase === 'pressed' || !el) {
        frameRef.current = null;
        return;
      }
      const rect = el.getBoundingClientRect();
      const delta = autoScrollDelta(press.lastClient.y - rect.top, rect.height);
      if (delta !== 0) {
        const before = el.scrollTop;
        el.scrollTop = before + delta;
        if (el.scrollTop !== before) showGhost(preview());
      }
      frameRef.current = requestAnimationFrame(step);
    }
    frameRef.current = requestAnimationFrame(step);
  }, [scrollRef, preview, showGhost]);

  const begin = useCallback((phase: Exclude<Phase, 'pressed'>) => {
    const press = pressRef.current;
    if (!press) return;
    if (press.longPressTimer != null) window.clearTimeout(press.longPressTimer);
    press.longPressTimer = null;
    press.phase = phase;
    showGhost(preview());
    startAutoScroll();
  }, [startAutoScroll, preview, showGhost]);

  const commit = useCallback(() => {
    const press = pressRef.current;
    const shape = preview();
    if (!press || !shape) return;
    const { timeZone: tz, onCreateRange: create, onRescheduleOccurrence: reschedule } = latest.current;
    if (shape.kind === 'create') {
      create?.({ date: shape.timing.date, startMinute: shape.timing.startMinute, endMinute: shape.timing.startMinute + shape.timing.durationMinutes });
      return;
    }
    const occurrence = press.block?.segment.occurrence;
    if (!occurrence || !press.origin || sameTiming(press.origin, shape.timing)) return;
    const after: OccurrenceSchedule = {
      ...shape.timing,
      start: new Date(fromZonedPoint(shape.timing.date, shape.timing.startMinute, tz)).toISOString(),
    };
    const change: OccurrenceReschedule = {
      kind: shape.kind,
      occurrence,
      scope: occurrence.is_recurring ? 'occurrence' : 'event',
      before: { ...press.origin, start: occurrence.start },
      after,
    };
    reschedule?.(change);
  }, [preview]);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId !== press.pointerId) return;
      press.lastClient = { x: e.clientX, y: e.clientY };
      if (press.phase !== 'pressed') {
        showGhost(preview());
        return;
      }
      const decision = decideGesture({
        onEventBlock: press.block != null,
        onResizeHandle: press.edge != null,
        start: press.startClient,
        current: press.lastClient,
        elapsedMs: performance.now() - press.startTime,
      });
      if (press.block) {
        if (decision === 'resize') begin('resize');
        else if (decision === 'drag') begin('move');
      } else if (decision === 'scroll') {
        // 指で空き枠を押して動かした = スクロール（ブラウザに任せる）。マウスは範囲作り。
        if (press.pointerType === 'touch') finish();
        else begin('create');
      }
    };
    const onUp = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId !== press.pointerId) return;
      if (press.phase !== 'pressed') {
        press.lastClient = { x: e.clientX, y: e.clientY };
        commit();
        suppressClickUntil.current = performance.now() + SUPPRESS_CLICK_MS;
      }
      finish();
    };
    const onCancel = (e: PointerEvent) => {
      if (pressRef.current && e.pointerId === pressRef.current.pointerId) finish();
    };
    // 2 本目の指が触れたら中止（移植元 `touchCount > 1`）。
    const onOtherDown = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId === press.pointerId) return;
      if (press.phase !== 'pressed') suppressClickUntil.current = performance.now() + SUPPRESS_CLICK_MS;
      finish();
    };
    const onKey = (e: KeyboardEvent) => {
      const press = pressRef.current;
      if (e.key !== 'Escape' || !press || press.phase === 'pressed') return;
      e.preventDefault();
      suppressClickUntil.current = performance.now() + SUPPRESS_CLICK_MS;
      finish();
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    window.addEventListener('pointerdown', onOtherDown, true);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
      window.removeEventListener('pointerdown', onOtherDown, true);
      window.removeEventListener('keydown', onKey);
    };
  }, [begin, commit, finish, preview, showGhost]);

  // 指で長押ししてから引いたときに、ブラウザのスクロールを止める（空き枠は touch-action で縦の
  // スクロールを許しているので、ドラッグ中だけ touchmove を打ち消す）。
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onTouchMove = (e: TouchEvent) => {
      if (pressRef.current && pressRef.current.phase !== 'pressed' && e.cancelable) e.preventDefault();
    };
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    return () => el.removeEventListener('touchmove', onTouchMove);
  }, [scrollRef]);

  useEffect(() => finish, [finish]);

  const startPress = (e: React.PointerEvent<HTMLElement>, block: WeekEventBlock | null, edge: 'top' | 'bottom' | null) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return false;
    if (pressRef.current) return false;
    const client = { x: e.clientX, y: e.clientY };
    const at = locate(client);
    if (!at) return false;
    pressRef.current = {
      pointerId: e.pointerId,
      pointerType: e.pointerType,
      phase: 'pressed',
      startClient: client,
      lastClient: client,
      startTime: performance.now(),
      startDate: at.date,
      startY: at.y,
      block,
      edge,
      origin: block ? originOf(block.segment.occurrence, latest.current.timeZone) : null,
      longPressTimer: null,
    };
    return true;
  };

  /** 予定を押した。`edge` は上端・下端のつかみか（日をまたいで続く側の端は null で渡す）。 */
  const onEventPointerDown = (e: React.PointerEvent<HTMLElement>, block: WeekEventBlock, edge: 'top' | 'bottom' | null) => {
    if (!latest.current.onRescheduleOccurrence) return;
    if (startPress(e, block, edge) && e.pointerType === 'mouse') e.preventDefault(); // 文字の選択を始めない
  };

  /** 時間グリッドの空き枠を押した。 */
  const onGridPointerDown = (e: React.PointerEvent<HTMLElement>) => {
    if (!latest.current.onCreateRange || !startPress(e, null, null)) return;
    if (e.pointerType === 'mouse') {
      e.preventDefault();
      return;
    }
    if (e.pointerType === 'touch') {
      const current = pressRef.current;
      if (current) {
        current.longPressTimer = window.setTimeout(() => {
          const p = pressRef.current;
          if (p !== current || p.phase !== 'pressed') return;
          const decision = decideGesture({
            onEventBlock: false, onResizeHandle: false, start: p.startClient, current: p.lastClient,
            elapsedMs: performance.now() - p.startTime,
          });
          if (decision === 'longPress') begin('create');
        }, LONG_PRESS_MS);
      }
    }
  };

  /** ドラッグを離した直後のクリック（選択・作成）を無視するか。 */
  const shouldSuppressClick = () => performance.now() < suppressClickUntil.current;

  return { ghost, onEventPointerDown, onGridPointerDown, shouldSuppressClick };
};
