// @vitest-environment jsdom
/** The maintenance screen (ADR-0075): edge text first, app text as fallback, re-check by button and by timer. */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MaintenanceGate, MaintenanceScreen, RECHECK_INTERVAL_MS, formatUntil, utcOffsetLabel } from './MaintenanceScreen';
import { reportOutage, reportReopened, resetOutageForTests, type Outage } from '../pwa/maintenance';

const outage = (over: Partial<Outage> = {}): Outage => ({
  reason: 'maintenance',
  title: null,
  body: null,
  message: null,
  until: null,
  ...over,
});

beforeEach(() => {
  localStorage.setItem('app.language', 'en');
});

afterEach(() => {
  cleanup();
  resetOutageForTests();
  localStorage.clear();
  vi.useRealTimers();
});

describe('MaintenanceScreen', () => {
  it("shows the edge's heading, text and reason", () => {
    render(
      <MaintenanceScreen
        outage={outage({ title: 'Release in progress', body: 'A few minutes', message: 'v2' })}
        check={async () => 'closed'}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Release in progress' })).toBeTruthy();
    expect(screen.getByText('A few minutes')).toBeTruthy();
    expect(screen.getByText('Reason: v2')).toBeTruthy();
  });

  it("falls back to the app's own text, per reason", () => {
    const { rerender } = render(<MaintenanceScreen outage={outage()} check={async () => 'closed'} />);
    expect(screen.getByRole('heading', { name: 'Under maintenance' })).toBeTruthy();
    rerender(<MaintenanceScreen outage={outage({ reason: 'stopped' })} check={async () => 'closed'} />);
    expect(screen.getByRole('heading', { name: 'Service stopped' })).toBeTruthy();
  });

  it('checks on the button and every minute', async () => {
    vi.useFakeTimers();
    const check = vi.fn(async () => 'closed');
    render(<MaintenanceScreen outage={outage()} check={check} />);
    fireEvent.click(screen.getByRole('button', { name: 'Check now' }));
    expect(check).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(RECHECK_INTERVAL_MS);
    });
    expect(check).toHaveBeenCalledTimes(2);
  });
});

describe('MaintenanceGate', () => {
  it('appears while closed and goes away once open', () => {
    render(<MaintenanceGate check={async () => 'closed'} />);
    expect(screen.queryByRole('alert')).toBeNull();
    act(() => reportOutage(outage()));
    expect(screen.getByRole('alert')).toBeTruthy();
    act(() => reportReopened());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('formatUntil', () => {
  it('adds the UTC offset and ignores unreadable values', () => {
    const text = formatUntil('2026-11-20T10:00:00Z', 'en-US');
    expect(text).toContain(`(${utcOffsetLabel(new Date('2026-11-20T10:00:00Z'))})`);
    expect(formatUntil('soon', 'en-US')).toBeNull();
    expect(formatUntil(null, 'en-US')).toBeNull();
  });
});
