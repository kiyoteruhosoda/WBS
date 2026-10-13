// PC の自動記録の規則の入力欄（task #381、ADR-0043）。画面の部品から切り離した純関数。
import type { EditableTrackingRule, TrackingRuleWrite } from '../types';

export interface RuleForm {
  app: string;
  titleContains: string;
  taskId: number | null;
}

export const emptyRuleForm: RuleForm = { app: '', titleContains: '', taskId: null };

/**
 * `/tracking-rules/new?app=EXCEL.EXE&title=見積` の欄（WinTrack の「この区間から規則を作る」が開く）。
 * 無い欄は空のまま。タスクは利用者が選ぶ。
 */
export const ruleFormFromQuery = (search: string): RuleForm => {
  const params = new URLSearchParams(search);
  const app = (params.get('app') ?? '').trim();
  const titleContains = (params.get('title') ?? '').trim();
  return { app, titleContains, taskId: null };
};

export const ruleFormOf = (rule: EditableTrackingRule): RuleForm => ({
  app: rule.app ?? '',
  titleContains: rule.title_contains ?? '',
  taskId: rule.task_available ? rule.task_id : null,
});

export type RuleFormProblem = 'needsCondition' | 'needsTask';

/** 送れない理由（送れるなら null）。アプリと表題の両方が空の規則は何にでも当たるので作らせない。 */
export const ruleFormProblem = (form: RuleForm): RuleFormProblem | null => {
  if (!form.app.trim() && !form.titleContains.trim()) return 'needsCondition';
  if (form.taskId == null) return 'needsTask';
  return null;
};

/** 送る形。空の欄は null（「問わない」）。 */
export const ruleWriteOf = (form: RuleForm): TrackingRuleWrite => ({
  app: form.app.trim() || null,
  title_contains: form.titleContains.trim() || null,
  task_id: form.taskId ?? 0,
});

/** 1 つ上・下へ動かした後の順（端なら変えずに null）。 */
export const movedOrder = (ids: readonly number[], id: number, step: -1 | 1): number[] | null => {
  const index = ids.indexOf(id);
  const target = index + step;
  if (index < 0 || target < 0 || target >= ids.length) return null;
  const next = [...ids];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
};
