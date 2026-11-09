/**
 * 新しい版の知らせ（帯）の高さを、上に貼り付く部品へ渡す（ADR-0072）。
 *
 * 帯は画面の外枠（ルーター）より前に置くので、ヘッダーや左のメニューとは同じ箱に入れられない。
 * そこで帯の高さを `<html>` の CSS 変数 `--update-bar-height` に入れ、貼り付く部品は
 * `top: var(--update-bar-height, 0px)` で帯の真下に付く。狭い画面で折り返すと高さが変わるので見張る。
 */
export const UPDATE_BAR_HEIGHT_VAR = '--update-bar-height';

/** 貼り付く部品の `top` に使う値（帯が出ていなければ 0）。 */
export const BELOW_UPDATE_BAR = `var(${UPDATE_BAR_HEIGHT_VAR}, 0px)`;

type Bar = { readonly offsetHeight: number };
type Root = { readonly style: Pick<CSSStyleDeclaration, 'setProperty' | 'removeProperty'> };
type ResizeWatcher = { observe(target: never): void; disconnect(): void };
type ResizeWatcherFactory = (onResize: () => void) => ResizeWatcher | null;

const browserResizeWatcher: ResizeWatcherFactory = (onResize) =>
  // jsdom など ResizeObserver の無い所では見張らない（高さは最初に 1 回渡してある）
  typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onResize);

/** 帯の高さを渡し始める。返した関数で見張りを止め、変数を外す（帯が消えたとき）。 */
export function followUpdateBarHeight(
  bar: Bar,
  root: Root,
  watchResize: ResizeWatcherFactory = browserResizeWatcher,
): () => void {
  const publish = () => {
    root.style.setProperty(UPDATE_BAR_HEIGHT_VAR, `${String(bar.offsetHeight)}px`);
  };
  publish();
  const watcher = watchResize(publish);
  watcher?.observe(bar as never);
  return () => {
    watcher?.disconnect();
    root.style.removeProperty(UPDATE_BAR_HEIGHT_VAR);
  };
}
