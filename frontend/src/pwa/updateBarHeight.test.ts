import { describe, expect, it } from 'vitest';
import { UPDATE_BAR_HEIGHT_VAR, followUpdateBarHeight } from './updateBarHeight';

function fakeRoot() {
  const props = new Map<string, string>();
  return {
    props,
    style: {
      setProperty: (name: string, value: string | null) => {
        props.set(name, value ?? '');
      },
      removeProperty: (name: string) => {
        const old = props.get(name) ?? '';
        props.delete(name);
        return old;
      },
    },
  };
}

describe('passing the bar height to sticky components', () => {
  it('passes the height only while shown and removes it when gone', () => {
    const root = fakeRoot();
    const stop = followUpdateBarHeight({ offsetHeight: 48 }, root, () => null);

    expect(root.props.get(UPDATE_BAR_HEIGHT_VAR)).toBe('48px');

    stop();

    expect(root.props.has(UPDATE_BAR_HEIGHT_VAR)).toBe(false);
  });

  it('re-passes the height when wrapping changes it, and stops observing when stopped', () => {
    const root = fakeRoot();
    const bar = { offsetHeight: 48 };
    let onResize = () => {};
    let disconnected = false;
    const stop = followUpdateBarHeight(bar, root, (callback) => {
      onResize = callback;
      return { observe: () => {}, disconnect: () => { disconnected = true; } };
    });

    bar.offsetHeight = 84;
    onResize();
    expect(root.props.get(UPDATE_BAR_HEIGHT_VAR)).toBe('84px');

    stop();
    expect(disconnected).toBe(true);
  });
});
