import type React from 'react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PointerPoint } from '../../calendar/weekGestures';
import { LONG_PRESS_MS, autoScrollDelta, decideGesture } from '../../calendar/weekGestures';
import type { WeekEventBlock } from '../../calendar/weekLayout';
import type { EntrySegment } from '../../closing/closingBoard';
import { entryEndMs, entryStartMs } from '../../closing/closingBoard';
import type { EntryRange } from '../../closing/closingRequests';
import {
  draggedEntryRange, entryCreateRange, laneIndexAt, sameRange, zonedInstant,
} from '../../closing/entryGestures';

// 締めの画面の打刻のドラッグ（task #161 / ADR-0015）。週表示の `useWeekDrag` と同じ道（ポインタイベントだけで
// 追う・8px 動けば移動・端のつかみを縦に動かせば伸ばす・指は長押しで空き時間から作る・Esc で取り消す）で、
// 違いは「右の打刻の列だけを相手にする」「秒を保つ」「Shift で 1 分刻み」。

/** 打刻の列（各日の右側）に ClosingGrid が付ける印。 */
export const ENTRY_LANE_ATTRIBUTE = 'data-entry-lane';

const SUPPRESS_CLICK_MS = 300;

export interface ClosingDragGhost {
  kind: 'create' | 'move' | 'resize';
  /** 動かしている打刻。作るときは null */
  entryId: number | null;
  range: EntryRange;
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
  startDate: string;
  startY: number;
  block: WeekEventBlock<EntrySegment> | null;
  edge: 'top' | 'bottom' | null;
  original: EntryRange | null;
  fine: boolean;
  longPressTimer: number | null;
}

interface Options {
  timeZone: string;
  nowMs: number;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  /** 確定済みの期間では null（ドラッグしない） */
  onReschedule: ((entryId: number, range: EntryRange) => void) | null;
  onCreate: ((range: EntryRange) => void) | null;
}

export const useClosingDrag = ({ timeZone, nowMs, scrollRef, onReschedule, onCreate }: Options) => {
  const [ghost, setGhost] = useState<ClosingDragGhost | null>(null);
  const pressRef = useRef<Press | null>(null);
  const ghostRef = useRef<ClosingDragGhost | null>(null);
  const frameRef = useRef<number | null>(null);
  const suppressClickUntil = useRef(0);
  const latest = useRef({ timeZone, nowMs, onReschedule, onCreate });
  useLayoutEffect(() => {
    latest.current = { timeZone, nowMs, onReschedule, onCreate };
  });

  const showGhost = useCallback((next: ClosingDragGhost | null) => {
    const current = ghostRef.current;
    if (current === next) return;
    if (current && next && current.kind === next.kind && current.entryId === next.entryId && sameRange(current.range, next.range)) return;
    ghostRef.current = next;
    setGhost(next);
  }, []);

  /** ポインタの位置 → いちばん近い打刻の列の日と、その日の 0:00 からの位置（px = 分）。 */
  const locate = useCallback((client: PointerPoint): { date: string; y: number } | null => {
    const lanes = Array.from(scrollRef.current?.querySelectorAll<HTMLElement>(`[${ENTRY_LANE_ATTRIBUTE}]`) ?? []);
    if (lanes.length === 0) return null;
    const rects = lanes.map((l) => l.getBoundingClientRect());
    const index = laneIndexAt(client.x, rects);
    const date = lanes[index]?.getAttribute(ENTRY_LANE_ATTRIBUTE);
    return date ? { date, y: client.y - rects[index].top } : null;
  }, [scrollRef]);

  const preview = useCallback((): ClosingDragGhost | null => {
    const press = pressRef.current;
    if (!press || press.phase === 'pressed') return null;
    const at = locate(press.lastClient);
    if (!at) return ghostRef.current;
    const tz = latest.current.timeZone;
    if (press.phase === 'create') {
      // 作る範囲は押した日の中だけ（日をまたいで作りたければ、作ってから伸ばす）
      const r = entryCreateRange(press.startY, at.y, press.fine);
      return {
        kind: 'create', entryId: null, leftRatio: 0, widthRatio: 1,
        range: { startMs: zonedInstant(press.startDate, r.startMinute, tz), endMs: zonedInstant(press.startDate, r.endMinute, tz) },
      };
    }
    const block = press.block;
    if (!block || !press.original) return null;
    const grabbed = { date: block.segment.date, startMinute: block.segment.startMinute, endMinute: block.segment.endMinute };
    const range = draggedEntryRange(press.phase, press.edge, press.original, grabbed, at.date, at.y - press.startY, tz, press.fine);
    return { kind: press.phase, entryId: block.segment.entry.id, range, leftRatio: block.leftRatio, widthRatio: block.widthRatio };
  }, [locate]);

  const finish = useCallback(() => {
    const press = pressRef.current;
    if (press?.longPressTimer != null) window.clearTimeout(press.longPressTimer);
    pressRef.current = null;
    if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    showGhost(null);
  }, [showGhost]);

  // 端に近い間は毎フレーム送る（縦も横も。期間は最大 16 日で横に長い）。
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
      const dy = autoScrollDelta(press.lastClient.y - rect.top, rect.height);
      const dx = autoScrollDelta(press.lastClient.x - rect.left, rect.width);
      if (dy !== 0 || dx !== 0) {
        const before = { top: el.scrollTop, left: el.scrollLeft };
        el.scrollTop = before.top + dy;
        el.scrollLeft = before.left + dx;
        if (el.scrollTop !== before.top || el.scrollLeft !== before.left) showGhost(preview());
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
    const { onCreate: create, onReschedule: reschedule } = latest.current;
    if (shape.kind === 'create') {
      create?.(shape.range);
      return;
    }
    if (shape.entryId == null || !press.original || sameRange(press.original, shape.range)) return;
    reschedule?.(shape.entryId, shape.range);
  }, [preview]);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId !== press.pointerId) return;
      press.lastClient = { x: e.clientX, y: e.clientY };
      press.fine = e.shiftKey;
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
        if (press.pointerType === 'touch') finish();
        else begin('create');
      }
    };
    const onUp = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId !== press.pointerId) return;
      if (press.phase !== 'pressed') {
        press.lastClient = { x: e.clientX, y: e.clientY };
        press.fine = e.shiftKey;
        commit();
        suppressClickUntil.current = performance.now() + SUPPRESS_CLICK_MS;
      }
      finish();
    };
    const onCancel = (e: PointerEvent) => {
      if (pressRef.current && e.pointerId === pressRef.current.pointerId) finish();
    };
    const onOtherDown = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press || e.pointerId === press.pointerId) return;
      if (press.phase !== 'pressed') suppressClickUntil.current = performance.now() + SUPPRESS_CLICK_MS;
      finish();
    };
    // Shift を押す・離すだけでも刻みを変えて描き直す
    const onShift = (e: KeyboardEvent) => {
      const press = pressRef.current;
      if (e.key !== 'Shift' || !press || press.phase === 'pressed') return;
      press.fine = e.type === 'keydown';
      showGhost(preview());
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
    window.addEventListener('keydown', onShift);
    window.addEventListener('keyup', onShift);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
      window.removeEventListener('pointerdown', onOtherDown, true);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('keydown', onShift);
      window.removeEventListener('keyup', onShift);
    };
  }, [begin, commit, finish, preview, showGhost]);

  // 指で長押ししてから引いたときに、ブラウザのスクロールを止める。
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;
    const onTouchMove = (e: TouchEvent) => {
      if (pressRef.current && pressRef.current.phase !== 'pressed' && e.cancelable) e.preventDefault();
    };
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    return () => el.removeEventListener('touchmove', onTouchMove);
  }, [scrollRef]);

  useEffect(() => finish, [finish]);

  const startPress = (e: React.PointerEvent<HTMLElement>, block: WeekEventBlock<EntrySegment> | null, edge: 'top' | 'bottom' | null) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return false;
    if (pressRef.current) return false;
    const client = { x: e.clientX, y: e.clientY };
    const at = locate(client);
    if (!at) return false;
    const entry = block?.segment.entry;
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
      original: entry ? { startMs: entryStartMs(entry), endMs: entryEndMs(entry, latest.current.nowMs) } : null,
      fine: e.shiftKey,
      longPressTimer: null,
    };
    return true;
  };

  /** 打刻を押した。走っている打刻は動かさない（終わりが決まっていない）。 */
  const onEntryPointerDown = (e: React.PointerEvent<HTMLElement>, block: WeekEventBlock<EntrySegment>, edge: 'top' | 'bottom' | null) => {
    if (!latest.current.onReschedule || block.segment.entry.is_running) return;
    if (startPress(e, block, edge) && e.pointerType === 'mouse') e.preventDefault();
  };

  /** 打刻の列の空き時間を押した。 */
  const onLanePointerDown = (e: React.PointerEvent<HTMLElement>) => {
    if (!latest.current.onCreate || !startPress(e, null, null)) return;
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

  const shouldSuppressClick = () => performance.now() < suppressClickUntil.current;

  return { ghost, onEntryPointerDown, onLanePointerDown, shouldSuppressClick };
};
