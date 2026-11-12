/**
 * Pass the height of the new-version notice bar to sticky components at the top (ADR-0072).
 *
 * The bar is placed before the screen frame (router), so it can't share a box with the header or the left menu.
 * So the bar height goes into the CSS variable `--update-bar-height` on `<html>`, and sticky components
 * attach right below it with `top: var(--update-bar-height, 0px)`. Wrapping on narrow screens changes the height, so it is observed.
 */
export const UPDATE_BAR_HEIGHT_VAR = '--update-bar-height';

/** Value for sticky components' `top` (0 when the bar is not shown). */
export const BELOW_UPDATE_BAR = `var(${UPDATE_BAR_HEIGHT_VAR}, 0px)`;

type Bar = { readonly offsetHeight: number };
type Root = { readonly style: Pick<CSSStyleDeclaration, 'setProperty' | 'removeProperty'> };
type ResizeWatcher = { observe(target: never): void; disconnect(): void };
type ResizeWatcherFactory = (onResize: () => void) => ResizeWatcher | null;

const browserResizeWatcher: ResizeWatcherFactory = (onResize) =>
  // No observing where ResizeObserver is missing, e.g. jsdom (the height was already passed once)
  typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onResize);

/** Start passing the bar height. The returned function stops observing and removes the variable (when the bar goes away). */
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
