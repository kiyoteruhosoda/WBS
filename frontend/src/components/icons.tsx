import React from 'react';

// デザイン仕様: インラインSVG viewBox 24 / fill:none / stroke=文脈色 / stroke-width 1.8〜2.6 / round
interface IconProps {
  size?: number;
  stroke?: string;
  strokeWidth?: number;
}

const base = (
  { size = 20, stroke = 'currentColor', strokeWidth = 1.8 }: IconProps,
  children: React.ReactNode,
) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={stroke}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {children}
  </svg>
);

export const GridIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <rect x="4" y="4" width="6.5" height="6.5" rx="1.5" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" />
  </>
));

export const CheckListIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M4 6.5l1.5 1.5L8 5.5" />
    <path d="M11 7h9" />
    <path d="M4 13.5l1.5 1.5L8 12.5" />
    <path d="M11 14h9" />
    <path d="M11 20h9" />
    <circle cx="5.8" cy="20" r="0.4" />
  </>
));

export const BarsIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M4 6h10" />
    <path d="M8 12h12" />
    <path d="M4 18h7" />
  </>
));

export const CalendarIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <rect x="4" y="5.5" width="16" height="15" rx="2" />
    <path d="M4 10h16" />
    <path d="M8.5 3.5v3.5" />
    <path d="M15.5 3.5v3.5" />
  </>
));

export const TodayIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <rect x="4" y="5.5" width="16" height="15" rx="2" />
    <path d="M4 10h16" />
    <path d="M8.5 3.5v3.5" />
    <path d="M15.5 3.5v3.5" />
    <circle cx="12" cy="15" r="1.6" fill="currentColor" stroke="none" />
  </>
));

export const FolderIcon: React.FC<IconProps> = (p) => base(p, (
  <path d="M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7z" />
));

export const FlagIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M6 21V4" />
    <path d="M6 5h11l-2 3.5 2 3.5H6" />
  </>
));

export const InboxIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M4 13.5V17a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3.5" />
    <path d="M4 13.5h4.5l1.5 2.5h4l1.5-2.5H20" />
    <path d="M6.5 5h11l2.5 8.5" />
    <path d="M4 13.5L6.5 5" />
  </>
));

export const SlidersIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M4 8h10" />
    <path d="M18 8h2" />
    <circle cx="16" cy="8" r="2" />
    <path d="M4 16h2" />
    <path d="M10 16h10" />
    <circle cx="8" cy="16" r="2" />
  </>
));

export const SearchIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4.5 4.5" />
  </>
));

export const PlusIcon: React.FC<IconProps> = (p) => base({ strokeWidth: 2.4, ...p }, (
  <>
    <path d="M12 5v14" />
    <path d="M5 12h14" />
  </>
));

export const CheckIcon: React.FC<IconProps> = (p) => base({ strokeWidth: 2.6, ...p }, (
  <path d="M5 12.5l4.5 4.5L19 7" />
));

export const WarningTriangleIcon: React.FC<IconProps> = (p) => base({ strokeWidth: 2, ...p }, (
  <>
    <path d="M12 4.5L21 19.5H3L12 4.5z" />
    <path d="M12 10.5v4" />
    <circle cx="12" cy="17" r="0.4" />
  </>
));

export const ChevronLeftIcon: React.FC<IconProps> = (p) => base({ strokeWidth: 2, ...p }, (
  <path d="M14.5 6l-6 6 6 6" />
));

export const ChevronRightIcon: React.FC<IconProps> = (p) => base({ strokeWidth: 2, ...p }, (
  <path d="M9.5 6l6 6-6 6" />
));

export const TrashIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M4.5 6.5h15" />
    <path d="M9 6.5V4.8A1.3 1.3 0 0 1 10.3 3.5h3.4A1.3 1.3 0 0 1 15 4.8v1.7" />
    <path d="M6.5 6.5l.8 12.2a1.6 1.6 0 0 0 1.6 1.5h6.2a1.6 1.6 0 0 0 1.6-1.5l.8-12.2" />
    <path d="M10 10.5v6" />
    <path d="M14 10.5v6" />
  </>
));

export const SwapIcon: React.FC<IconProps> = (p) => base(p, (
  <>
    <path d="M4 8h13" />
    <path d="M14 4.5L17.5 8 14 11.5" />
    <path d="M20 16H7" />
    <path d="M10 12.5L6.5 16l3.5 3.5" />
  </>
));
