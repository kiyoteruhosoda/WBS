import { describe, expect, it } from 'vitest';
import type { TeamCalendar } from '../types';
import { DEFAULT_PROJECT_DAYS, projectDaysOf, workingDaysBetween, worksOn } from './projectCalendarDays';

const calendar: TeamCalendar = {
  project_id: 2, root_project_id: 1, can_manage: true,
  workdays: ['MO', 'TU', 'WE', 'TH', 'FR'],
  days_off: [{ day: '2026-11-03', name: '文化の日', project_id: 1, inherited: true }],
  extra_workdays: [{ day: '2026-11-07', name: null, project_id: 2, inherited: false }],
  leave: [],
};

describe('projectCalendarDays', () => {
  it('works on weekdays, not on days off, and on extra workdays', () => {
    const days = projectDaysOf(calendar);
    expect(worksOn(days, '2026-11-02')).toBe(true); // Mon
    expect(worksOn(days, '2026-11-03')).toBe(false); // Culture Day (holiday)
    expect(worksOn(days, '2026-11-07')).toBe(true); // Sat, working day
    expect(worksOn(days, '2026-11-08')).toBe(false); // Sun
    expect(days.daysOff.get('2026-11-03')).toBe('文化の日');
  });

  it('counts working days of a plan with the project calendar', () => {
    // 11/2 (Mon) – 11/8 (Sun): Mon, Wed, Thu, Fri, Sat (working day)
    expect(workingDaysBetween(projectDaysOf(calendar), '2026-11-02', '2026-11-08')).toBe(5);
    expect(workingDaysBetween(DEFAULT_PROJECT_DAYS, '2026-11-02', '2026-11-08')).toBe(5);
  });

  it('falls back to Monday to Friday without a calendar', () => {
    expect(projectDaysOf(undefined)).toBe(DEFAULT_PROJECT_DAYS);
    expect(worksOn(DEFAULT_PROJECT_DAYS, '2026-11-07')).toBe(false);
  });
});
