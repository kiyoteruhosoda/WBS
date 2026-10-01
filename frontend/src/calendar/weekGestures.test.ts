import { describe, expect, it } from 'vitest';
import {
  AUTO_SCROLL_MAX_STEP_PX, autoScrollDelta, createRange, dayIndexAt, decideGesture, formatTimingRange, ghostPieces,
  moveTiming, resizeEdgeAt, resizeTiming, sameTiming, snapToHalfHour, snapToQuarterHour, tapCreateMinute,
} from './weekGestures';
import type { GestureInput } from './weekGestures';
import { hm } from './testOccurrences';

const gesture = (overrides: Partial<GestureInput>) => decideGesture({
  onEventBlock: false, onResizeHandle: false, start: { x: 0, y: 0 }, current: { x: 0, y: 0 }, elapsedMs: 0, ...overrides,
});

// 移植元 NolumiaSchedulerTest/WeekInteractionServicesTests.cs を写したもの＋足したもの。
describe('decideGesture（WeekGestureArbitrationService）', () => {
  it('タップとドラッグの誤判定を防止する', () => {
    expect(gesture({ onEventBlock: true, current: { x: 3, y: 3 }, elapsedMs: 100 })).toBe('tap');
    expect(gesture({ onEventBlock: true, current: { x: 12, y: 1 }, elapsedMs: 200 })).toBe('drag');
  });

  it('リサイズは縦方向優先で判定される', () => {
    expect(gesture({ onEventBlock: true, onResizeHandle: true, current: { x: 1, y: 12 }, elapsedMs: 300 })).toBe('resize');
  });

  it('つかみでも横へ動かせば移動', () => {
    expect(gesture({ onEventBlock: true, onResizeHandle: true, current: { x: 12, y: 9 }, elapsedMs: 100 })).toBe('drag');
  });

  it('しきい値は 8px・250ms・300ms', () => {
    expect(gesture({ onEventBlock: true, current: { x: 0, y: 7.9 } })).toBe('tap');
    expect(gesture({ onEventBlock: true, current: { x: 0, y: 8 } })).toBe('drag');
    expect(gesture({ current: { x: 2, y: 2 }, elapsedMs: 250 })).toBe('tap');
    expect(gesture({ current: { x: 2, y: 2 }, elapsedMs: 280 })).toBe('scroll');
    expect(gesture({ current: { x: 2, y: 2 }, elapsedMs: 300 })).toBe('longPress');
    expect(gesture({ onEventBlock: true, current: { x: 2, y: 2 }, elapsedMs: 280 })).toBe('none');
  });

  it('空き枠を動かしたらスクロール、2 本目の指で中止', () => {
    expect(gesture({ current: { x: 0, y: 30 }, elapsedMs: 50 })).toBe('scroll');
    expect(gesture({ onEventBlock: true, current: { x: 0, y: 30 }, touchCount: 2 })).toBe('cancel');
  });
});

describe('resizeEdgeAt（WeekCalendarView.EdgeAt）', () => {
  it('上下 10px がつかみ', () => {
    expect(resizeEdgeAt(0, 60)).toBe('top');
    expect(resizeEdgeAt(10, 60)).toBe('top');
    expect(resizeEdgeAt(11, 60)).toBeNull();
    expect(resizeEdgeAt(49, 60)).toBeNull();
    expect(resizeEdgeAt(50, 60)).toBe('bottom');
  });

  it('小さい塊は高さの 1/3 まで（真ん中で動かせる）', () => {
    expect(resizeEdgeAt(5, 15)).toBe('top');
    expect(resizeEdgeAt(6, 15)).toBeNull();
    expect(resizeEdgeAt(9, 15)).toBeNull();
    expect(resizeEdgeAt(10, 15)).toBe('bottom');
  });
});

describe('autoScrollDelta（WeekAutoScrollService）', () => {
  it('エッジ近傍でオートスクロール量が発生する', () => {
    expect(autoScrollDelta(4, 600)).toBeLessThan(0);
    expect(autoScrollDelta(300, 600)).toBe(0);
    expect(autoScrollDelta(598, 600)).toBeGreaterThan(0);
  });

  it('端 48px の内側だけ、深さの 0.2 倍で 2〜24px', () => {
    expect(autoScrollDelta(48, 600)).toBe(0);
    expect(autoScrollDelta(552, 600)).toBe(0);
    expect(autoScrollDelta(47, 600)).toBe(-2);
    expect(autoScrollDelta(8, 600)).toBe(-8);
    expect(autoScrollDelta(-500, 600)).toBe(-AUTO_SCROLL_MAX_STEP_PX);
    expect(autoScrollDelta(1200, 600)).toBe(AUTO_SCROLL_MAX_STEP_PX);
  });
});

describe('丸め（WeekInteractionMapper）', () => {
  // 移植元の試験は四捨五入のときのまま（9:20 → 9:30）残っている。本体は 3c362fa で「押した枠の頭」へ
  // 切り下げに変わったので、こちらは本体に合わせる。
  it('タップ作成は15分45分を0分30分に丸める（押した枠の頭）', () => {
    expect(tapCreateMinute(hm(9, 10))).toBe(hm(9));
    expect(tapCreateMinute(hm(9, 20))).toBe(hm(9));
    expect(tapCreateMinute(hm(9, 40))).toBe(hm(9, 30));
    expect(tapCreateMinute(hm(9, 50))).toBe(hm(9, 30));
  });

  it('タップ作成では15分45分の境界が生成されない', () => {
    for (let minute = 0; minute <= 1439; minute++) {
      const snapped = tapCreateMinute(minute);
      expect(snapped % 60 === 15 || snapped % 60 === 45).toBe(false);
    }
  });

  it('タップ作成はグリッドの外でも日の中に収める', () => {
    expect(tapCreateMinute(-20)).toBe(0);
    expect(tapCreateMinute(5000)).toBe(hm(23, 30));
  });

  it('15 分は四捨五入、30 分は切り下げ', () => {
    expect(snapToQuarterHour(7)).toBe(0);
    expect(snapToQuarterHour(8)).toBe(15);
    expect(snapToQuarterHour(hm(9, 52))).toBe(hm(9, 45));
    expect(snapToQuarterHour(hm(9, 53))).toBe(hm(10));
    expect(snapToHalfHour(hm(9, 59))).toBe(hm(9, 30));
  });

  it('横位置から日の列（外へ出たら端の列）', () => {
    expect(dayIndexAt(0, 100, 7)).toBe(0);
    expect(dayIndexAt(99, 100, 7)).toBe(0);
    expect(dayIndexAt(100, 100, 7)).toBe(1);
    expect(dayIndexAt(-30, 100, 7)).toBe(0);
    expect(dayIndexAt(900, 100, 7)).toBe(6);
    expect(dayIndexAt(450, 100, 5)).toBe(4);
  });
});

describe('createRange（空き枠のドラッグで作る範囲）', () => {
  it('押した枠から指している枠まで、30 分単位', () => {
    expect(createRange(hm(9, 10), hm(9, 20))).toEqual({ startMinute: hm(9), endMinute: hm(9, 30) });
    expect(createRange(hm(9, 10), hm(10, 40))).toEqual({ startMinute: hm(9), endMinute: hm(11) });
  });

  it('上へ引いてもよい', () => {
    expect(createRange(hm(14, 5), hm(12, 50))).toEqual({ startMinute: hm(12, 30), endMinute: hm(14, 30) });
  });

  it('日の外へ出たら 0:00 / 24:00 で止める', () => {
    expect(createRange(hm(1), -200)).toEqual({ startMinute: 0, endMinute: hm(1, 30) });
    expect(createRange(hm(23), 3000)).toEqual({ startMinute: hm(23), endMinute: 1440 });
  });
});

const DAY = '2026-05-04';

describe('moveTiming（ドラッグで動かす）', () => {
  const origin = { date: DAY, startMinute: hm(9), durationMinutes: 60 };
  const grabbed = { date: DAY, startMinute: hm(9), endMinute: hm(10) };

  it('15 分に丸めて動かし、長さは変えない', () => {
    expect(moveTiming(origin, grabbed, DAY, 37)).toEqual({ date: DAY, startMinute: hm(9, 30), durationMinutes: 60 });
    expect(moveTiming(origin, grabbed, DAY, 7)).toEqual(origin);
  });

  it('日をまたいで動かす（日はポインタの下の列）', () => {
    expect(moveTiming(origin, grabbed, '2026-05-06', -60)).toEqual({ date: '2026-05-06', startMinute: hm(8), durationMinutes: 60 });
  });

  it('開始はその日の 0:00〜23:45 に収める', () => {
    expect(moveTiming(origin, grabbed, DAY, -900).startMinute).toBe(0);
    expect(moveTiming(origin, grabbed, DAY, 2000).startMinute).toBe(hm(23, 45));
  });

  it('翌日側の区間をつかんだら、回の開始も同じだけずれる', () => {
    // 5/4 22:00 から 4 時間（5/5 0:00〜2:00 の区間をつかんで 1 時間下げる）
    const night = { date: DAY, startMinute: hm(22), durationMinutes: 240 };
    const second = { date: '2026-05-05', startMinute: 0, endMinute: hm(2) };
    expect(moveTiming(night, second, '2026-05-05', 60)).toEqual({ date: DAY, startMinute: hm(23), durationMinutes: 240 });
    // 隣の日の列へ持っていけば 1 日ずれる
    expect(moveTiming(night, second, '2026-05-06', 0)).toEqual({ date: '2026-05-05', startMinute: hm(22), durationMinutes: 240 });
  });
});

describe('resizeTiming（端で伸ばし縮め）', () => {
  const origin = { date: DAY, startMinute: hm(9), durationMinutes: 60 };
  const grabbed = { date: DAY, startMinute: hm(9), endMinute: hm(10) };

  it('下端は終わりを動かす（15 分に丸める）', () => {
    expect(resizeTiming(origin, grabbed, 'bottom', 38)).toEqual({ date: DAY, startMinute: hm(9), durationMinutes: 105 });
  });

  it('上端は開始を動かし、終わりはそのまま', () => {
    expect(resizeTiming(origin, grabbed, 'top', -45)).toEqual({ date: DAY, startMinute: hm(8, 15), durationMinutes: 105 });
  });

  it('最短 15 分', () => {
    expect(resizeTiming(origin, grabbed, 'bottom', -200)).toEqual({ date: DAY, startMinute: hm(9), durationMinutes: 15 });
    expect(resizeTiming(origin, grabbed, 'top', 200)).toEqual({ date: DAY, startMinute: hm(9, 45), durationMinutes: 15 });
  });

  it('その日の 0:00〜24:00 に収める', () => {
    expect(resizeTiming(origin, grabbed, 'top', -2000)).toEqual({ date: DAY, startMinute: 0, durationMinutes: hm(10) });
    expect(resizeTiming(origin, grabbed, 'bottom', 2000)).toEqual({ date: DAY, startMinute: hm(9), durationMinutes: hm(15) });
  });

  it('日をまたぐ回は、翌日側の下端で終わりを動かす', () => {
    const night = { date: DAY, startMinute: hm(22), durationMinutes: 240 };
    const second = { date: '2026-05-05', startMinute: 0, endMinute: hm(2) };
    expect(resizeTiming(night, second, 'bottom', 60)).toEqual({ date: DAY, startMinute: hm(22), durationMinutes: 300 });
  });

  it('長さ 0 の回は描いている下端（60 分の枠）から伸ばす', () => {
    const reminder = { date: DAY, startMinute: hm(12), durationMinutes: 0 };
    expect(resizeTiming(reminder, { date: DAY, startMinute: hm(12), endMinute: hm(13) }, 'bottom', 30))
      .toEqual({ date: DAY, startMinute: hm(12), durationMinutes: 90 });
  });
});

describe('ゴースト', () => {
  it('日をまたぐ時刻は日ごとに割る', () => {
    expect(ghostPieces({ date: DAY, startMinute: hm(22), durationMinutes: 240 })).toEqual([
      { date: DAY, startMinute: hm(22), endMinute: 1440 },
      { date: '2026-05-05', startMinute: 0, endMinute: hm(2) },
    ]);
  });

  it('長さ 0 でも 15 分の高さで描く', () => {
    expect(ghostPieces({ date: DAY, startMinute: hm(12), durationMinutes: 0 })).toEqual([
      { date: DAY, startMinute: hm(12), endMinute: hm(12, 15) },
    ]);
  });

  it('時刻の表示（翌 0:00 で終わるなら 24:00）', () => {
    expect(formatTimingRange({ date: DAY, startMinute: hm(9), durationMinutes: 90 })).toBe('09:00 – 10:30');
    expect(formatTimingRange({ date: DAY, startMinute: hm(23), durationMinutes: 60 })).toBe('23:00 – 24:00');
    expect(formatTimingRange({ date: DAY, startMinute: hm(22), durationMinutes: 240 })).toBe('22:00 – 02:00');
  });

  it('同じ時刻か', () => {
    expect(sameTiming({ date: DAY, startMinute: 0, durationMinutes: 15 }, { date: DAY, startMinute: 0, durationMinutes: 15 })).toBe(true);
    expect(sameTiming({ date: DAY, startMinute: 0, durationMinutes: 15 }, { date: DAY, startMinute: 15, durationMinutes: 15 })).toBe(false);
  });
});
