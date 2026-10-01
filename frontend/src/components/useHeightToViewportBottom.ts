import { useCallback, useLayoutEffect, useState } from 'react';

/**
 * 箱の高さを「画面の下端まで」にする（広い画面のカレンダー・「今日」の時間グリッド）。
 *
 * `calc(100vh - 160px)` のように上の高さを決め打ちすると、上に締めの知らせ（ClosingNotice）が出たときだけ
 * その分ページ全体が下へはみ出し、外側と内側の 2 段のスクロールになる。箱の上端を実際に測って引く。
 * 上の物が後から出たり消えたりしても追うように、ページ全体の大きさの変化でも測り直す。
 *
 * `enabled` が false の間（狭い画面）は測らず `null` を返す（呼ぶ側の既定の高さのまま）。
 * `ref` は要素を受け取る関数（読み込み中の表示のあとで箱が現れても測れるように）。
 */
export const useHeightToViewportBottom = <T extends HTMLElement>(bottomGap: number, enabled: boolean) => {
  const [el, setEl] = useState<T | null>(null);
  const ref = useCallback((node: T | null) => setEl(node), []);
  const [height, setHeight] = useState<number | null>(null);

  useLayoutEffect(() => {
    if (!enabled || !el) {
      setHeight(null);
      return;
    }
    const update = () => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      setHeight(Math.floor(window.innerHeight - top - bottomGap));
    };
    update();
    window.addEventListener('resize', update);
    // 自分の高さが変わってもページの大きさは変わるが、上端は動かないので同じ値になり、繰り返さない。
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    observer?.observe(document.body);
    return () => {
      window.removeEventListener('resize', update);
      observer?.disconnect();
    };
  }, [el, bottomGap, enabled]);

  return { ref, height };
};
