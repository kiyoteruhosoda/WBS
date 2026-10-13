import client from './client';
import type { EditableTrackingRule, TrackingRuleWrite } from '../types';

// PC の自動記録の規則（task #381、ADR-0043）。PC の係が読む GET /tracking-rules とは別に、画面は /editor を読む
export const getEditableTrackingRules = async (): Promise<EditableTrackingRule[]> => {
  const { data } = await client.get<EditableTrackingRule[]>('/tracking-rules/editor');
  return data;
};

export const createTrackingRule = async (body: TrackingRuleWrite): Promise<EditableTrackingRule> => {
  const { data } = await client.post<EditableTrackingRule>('/tracking-rules', body);
  return data;
};

export const updateTrackingRule = async (id: number, body: TrackingRuleWrite): Promise<EditableTrackingRule> => {
  const { data } = await client.patch<EditableTrackingRule>(`/tracking-rules/${id}`, body);
  return data;
};

export const deleteTrackingRule = async (id: number): Promise<void> => {
  await client.delete(`/tracking-rules/${id}`);
};

/** 上からの順に並べ直す。 */
export const reorderTrackingRules = async (ruleIds: number[]): Promise<EditableTrackingRule[]> => {
  const { data } = await client.put<EditableTrackingRule[]>('/tracking-rules/order', { rule_ids: ruleIds });
  return data;
};
