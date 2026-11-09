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

describe('帯の高さを貼り付く部品へ渡す', () => {
  it('出ている間だけ高さを渡し、消えたら外す', () => {
    const root = fakeRoot();
    const stop = followUpdateBarHeight({ offsetHeight: 48 }, root, () => null);

    expect(root.props.get(UPDATE_BAR_HEIGHT_VAR)).toBe('48px');

    stop();

    expect(root.props.has(UPDATE_BAR_HEIGHT_VAR)).toBe(false);
  });

  it('折り返して高さが変わったら渡し直し、止めたら見張りもやめる', () => {
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
