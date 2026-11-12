import React from 'react';

/**
 * The app mark (shown on the login screen and above the menu).
 *
 * It has no artwork of its own and loads the same `favicon.svg` as the tab icon. The single source of truth is
 * `scripts/generate_pwa_icons.py`; changing the design or colors there changes the tab and
 * home-screen icons together with this mark (same approach as ADR-0053 in the fastapitemplate template).
 * Wherever the mark is needed, use this component instead of redrawing it.
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
