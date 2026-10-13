import { describe, expect, it } from 'vitest';
import type { EditableTrackingRule } from '../types';
import { movedOrder, ruleFormFromQuery, ruleFormOf, ruleFormProblem, ruleWriteOf } from './ruleForm';

const rule = (overrides: Partial<EditableTrackingRule> = {}): EditableTrackingRule => ({
  id: 1,
  position: 0,
  app: 'EXCEL.EXE',
  title_contains: null,
  task_id: 12,
  task_title: '見積書を作る',
  task_available: true,
  created_at: null,
  updated_at: null,
  ...overrides,
});

describe('ruleFormFromQuery', () => {
  it('fills the fields WinTrack sent and leaves the task to the person', () => {
    expect(ruleFormFromQuery('?app=EXCEL.EXE&title=%E8%A6%8B%E7%A9%8D')).toEqual({
      app: 'EXCEL.EXE', titleContains: '見積', taskId: null,
    });
  });

  it('leaves missing fields empty', () => {
    expect(ruleFormFromQuery('')).toEqual({ app: '', titleContains: '', taskId: null });
    expect(ruleFormFromQuery('?title=+%E8%A6%8B%E7%A9%8D+')).toEqual({ app: '', titleContains: '見積', taskId: null });
  });
});

describe('ruleFormOf', () => {
  it('drops a task the rule can no longer use, so a new one must be picked', () => {
    expect(ruleFormOf(rule()).taskId).toBe(12);
    expect(ruleFormOf(rule({ task_available: false })).taskId).toBeNull();
  });
});

describe('ruleFormProblem', () => {
  it('needs an app or a title, and a task', () => {
    expect(ruleFormProblem({ app: ' ', titleContains: '', taskId: 1 })).toBe('needsCondition');
    expect(ruleFormProblem({ app: 'code.exe', titleContains: '', taskId: null })).toBe('needsTask');
    expect(ruleFormProblem({ app: '', titleContains: 'WBS', taskId: 1 })).toBeNull();
  });
});

describe('ruleWriteOf', () => {
  it('sends blank fields as null', () => {
    expect(ruleWriteOf({ app: ' EXCEL.EXE ', titleContains: '  ', taskId: 3 })).toEqual({
      app: 'EXCEL.EXE', title_contains: null, task_id: 3,
    });
  });
});

describe('movedOrder', () => {
  it('swaps with the neighbour and stops at the ends', () => {
    expect(movedOrder([1, 2, 3], 2, -1)).toEqual([2, 1, 3]);
    expect(movedOrder([1, 2, 3], 2, 1)).toEqual([1, 3, 2]);
    expect(movedOrder([1, 2, 3], 1, -1)).toBeNull();
    expect(movedOrder([1, 2, 3], 3, 1)).toBeNull();
    expect(movedOrder([1, 2, 3], 9, 1)).toBeNull();
  });
});
