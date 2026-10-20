import { describe, expect, it } from 'vitest';
import { forecastGapKey, milestoneForecastIsPartial, showsOnGantt, taskForecastSpan } from './forecastView';

describe('forecastView', () => {
  it('gives a short word for every gap except finished', () => {
    expect(forecastGapKey('no_assignee')).toBe('forecast.gap.no_assignee');
    expect(forecastGapKey('waiting')).toBe('forecast.gap.waiting');
    expect(forecastGapKey('finished')).toBeNull();
    expect(forecastGapKey(null)).toBeNull();
  });

  it('builds the forecast span and carries the overdue days', () => {
    expect(taskForecastSpan({ forecast_start: '2026-11-09', forecast_finish: '2026-11-10', forecast_overdue_days: 4 }))
      .toEqual({ start: '2026-11-09', finish: '2026-11-10', overdueDays: 4 });
    expect(taskForecastSpan({ forecast_start: null, forecast_finish: '2026-11-10' }))
      .toEqual({ start: '2026-11-10', finish: '2026-11-10', overdueDays: 0 });
    expect(taskForecastSpan({ forecast_start: null, forecast_finish: null })).toBeNull();
  });

  it('shows a task on the gantt when it has a plan or a forecast', () => {
    expect(showsOnGantt({ start_date: null, due_date: null, forecast_finish: '2026-11-10' })).toBe(true);
    expect(showsOnGantt({ start_date: null, due_date: '2026-11-10', forecast_finish: null })).toBe(true);
    expect(showsOnGantt({ start_date: null, due_date: null, forecast_finish: null })).toBe(false);
  });

  it('marks a milestone forecast as partial when some tasks have none', () => {
    expect(milestoneForecastIsPartial({ forecast_unforecast_count: 2 })).toBe(true);
    expect(milestoneForecastIsPartial({ forecast_unforecast_count: 0 })).toBe(false);
  });
});
