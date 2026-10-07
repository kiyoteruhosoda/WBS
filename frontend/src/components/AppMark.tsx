import React from 'react';

/**
 * アプリの像（ログイン画面・メニューの上に出す）。
 *
 * 絵は持たず、タブのアイコンと同じ `favicon.svg` をそのまま読む。正本は
 * `scripts/generate_pwa_icons.py` の 1 本だけで、図柄や色を変えるとタブ・
 * ホーム画面のアイコンとこの像がいっしょに変わる（雛形 fastapitemplate の ADR-0053 と同じ作り）。
 * 像を足す場所でも絵を書き起こさず、この部品を使う。
 */
const AppMark: React.FC<{ size: number }> = ({ size }) => (
  <img
    src={`${import.meta.env.BASE_URL}favicon.svg`}
    width={size}
    height={size}
    alt=""
    style={{ display: 'block', flexShrink: 0 }}
  />
);

export default AppMark;
