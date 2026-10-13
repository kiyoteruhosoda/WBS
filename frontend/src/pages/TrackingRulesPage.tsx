// PC の自動記録の規則（WinTrack、task #381 / ADR-0043）。
// 「アプリが〜」「表題に〜を含む」→ タスク、を上から並べる。PC は上から最初に当てはまった規則を使う。
// `/tracking-rules/new?app=&title=` は欄を埋めた作成の画面を開く（WinTrack の「この区間から規則を作る」）。
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Alert, Box, Button, ButtonBase, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, TextField,
} from '@mui/material';
import {
  createTrackingRule, deleteTrackingRule, getEditableTrackingRules, reorderTrackingRules, updateTrackingRule,
} from '../api/trackingRules';
import { getTasks } from '../api/tasks';
import { getProjects } from '../api/projects';
import TaskPickerField from '../components/TaskPickerField';
import { ChevronDownIcon, PlusIcon, TrashIcon, WarningTriangleIcon } from '../components/icons';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import type { EditableTrackingRule } from '../types';
import {
  emptyRuleForm, formIsEverythingElse, isEverythingElse, movedOrder, ruleFormFromQuery, ruleFormOf, ruleFormProblem,
  ruleWriteOf,
  type RuleForm,
} from '../trackingRules/ruleForm';

const RULES_KEY = ['tracking-rules', 'editor'];

const TrackingRulesPage: React.FC = () => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: rules, isLoading, error } = useQuery({ queryKey: RULES_KEY, queryFn: getEditableTrackingRules });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: getProjects });
  // 規則は開いているタスクへだけ向けられる（閉じたタスクはサーバーが 422 で断る）
  const openTasks = useMemo(
    () => (tasks ?? []).filter((task) => task.status !== 'DONE' && task.status !== 'CANCELLED'),
    [tasks],
  );

  // /tracking-rules/new は、開いた URL の欄で作成の画面を開いた状態から始める
  const creatingFromUrl = location.pathname.endsWith('/new');
  const [editing, setEditing] = useState<EditableTrackingRule | null>(null);
  const [dialogOpen, setDialogOpen] = useState(creatingFromUrl);
  const [form, setForm] = useState<RuleForm>(creatingFromUrl ? ruleFormFromQuery(location.search) : emptyRuleForm);
  const [showProblem, setShowProblem] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<EditableTrackingRule | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: RULES_KEY });

  const closeDialog = () => {
    setDialogOpen(false);
    setEditing(null);
    // 作成の画面の URL を一覧へ戻す（再読み込みで同じ画面が開き直さないように）
    if (creatingFromUrl) navigate('/tracking-rules', { replace: true });
  };

  const save = useMutation({
    mutationFn: (value: RuleForm) =>
      editing ? updateTrackingRule(editing.id, ruleWriteOf(value)) : createTrackingRule(ruleWriteOf(value)),
    onSuccess: () => { void invalidate(); closeDialog(); },
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteTrackingRule(id),
    onSuccess: () => { void invalidate(); setDeleteTarget(null); },
  });
  const reorder = useMutation({
    mutationFn: reorderTrackingRules,
    onSuccess: (next) => qc.setQueryData(RULES_KEY, next),
  });

  const openNew = () => {
    setEditing(null);
    setForm(emptyRuleForm);
    setShowProblem(false);
    setDialogOpen(true);
  };
  const openEdit = (rule: EditableTrackingRule) => {
    setEditing(rule);
    setForm(ruleFormOf(rule));
    setShowProblem(false);
    setDialogOpen(true);
  };
  // 「それ以外すべて」はいつも最後で、並べ替えの外（ADR-0045）
  const movableIds = (rules ?? []).filter((r) => !isEverythingElse(r)).map((r) => r.id);
  const move = (rule: EditableTrackingRule, step: -1 | 1) => {
    const next = movedOrder(movableIds, rule.id, step);
    if (next) reorder.mutate(next);
  };
  const otherEverythingElse = (rules ?? []).some((r) => isEverythingElse(r) && r.id !== editing?.id);
  const submit = () => {
    if (ruleFormProblem(form, otherEverythingElse)) { setShowProblem(true); return; }
    save.mutate(form);
  };

  const problem = showProblem ? ruleFormProblem(form, otherEverythingElse) : null;
  const conditionOf = (rule: EditableTrackingRule): string => isEverythingElse(rule) ? t('trackingRules.everythingElse') : [
    rule.app ? t('trackingRules.conditionApp', { app: rule.app }) : t('trackingRules.anyApp'),
    rule.title_contains ? t('trackingRules.conditionTitle', { title: rule.title_contains }) : t('trackingRules.anyTitle'),
  ].join(' ・ ');

  return (
    <Box sx={{ maxWidth: 760 }}>
      <Box sx={{ fontSize: 13, color: ds.textSub, lineHeight: 1.7, mb: '14px' }}>{t('trackingRules.lead')}</Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: '14px' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('trackingRules.count', { count: rules?.length ?? 0 })}</Box>
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" startIcon={<PlusIcon size={16} />} onClick={openNew} sx={{ px: '18px' }} data-testid="tracking-rules-add">
          {t('trackingRules.new')}
        </Button>
      </Box>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {reorder.isError && <Alert severity="error" sx={{ mb: '12px' }}>{t('trackingRules.saveError')}</Alert>}

      {rules && (
        <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }} data-testid="tracking-rules">
          {rules.length === 0 && (
            <Box sx={{ textAlign: 'center', py: '32px', color: ds.textMuted, fontSize: 13 }}>{t('trackingRules.empty')}</Box>
          )}
          {rules.map((rule, index) => (
            <Box
              key={rule.id}
              sx={{
                display: 'flex', alignItems: 'center', gap: '6px', pl: '6px', pr: '6px',
                borderBottom: `1px solid ${ds.hairline}`, '&:last-of-type': { borderBottom: 'none' },
              }}
            >
              {isEverythingElse(rule) ? (
                // 並べ替えない（いつも最後）。上下のボタンの幅だけ空ける
                <Box sx={{ width: 32, flexShrink: 0 }} />
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
                  <IconButton
                    size="small" aria-label={t('trackingRules.moveUp')}
                    disabled={movableIds.indexOf(rule.id) === 0 || reorder.isPending}
                    onClick={() => move(rule, -1)} sx={{ color: ds.textSub, p: '4px' }}
                  >
                    <Box component="span" sx={{ display: 'inline-flex', transform: 'rotate(180deg)' }}><ChevronDownIcon size={16} /></Box>
                  </IconButton>
                  <IconButton
                    size="small" aria-label={t('trackingRules.moveDown')}
                    disabled={movableIds.indexOf(rule.id) === movableIds.length - 1 || reorder.isPending}
                    onClick={() => move(rule, 1)} sx={{ color: ds.textSub, p: '4px' }}
                  >
                    <ChevronDownIcon size={16} />
                  </IconButton>
                </Box>
              )}
              <ButtonBase
                onClick={() => openEdit(rule)}
                aria-label={t('trackingRules.editTitle')}
                sx={{
                  flex: 1, minWidth: 0, minHeight: 56, py: '8px', px: '6px', gap: '2px', borderRadius: '6px',
                  display: 'flex', flexDirection: 'column', alignItems: 'stretch', textAlign: 'left',
                  '&:hover': { bgcolor: ds.primaryPale },
                }}
              >
                <Box sx={{ fontSize: 13, color: ds.textSub, overflowWrap: 'anywhere' }}>
                  {!isEverythingElse(rule) && (
                    <Box component="span" sx={{ color: ds.textMuted, mr: '6px', fontVariantNumeric: 'tabular-nums' }}>{index + 1}</Box>
                  )}
                  <Box component="span" sx={isEverythingElse(rule) ? { fontWeight: 700, color: ds.text } : undefined}>
                    {conditionOf(rule)}
                  </Box>
                </Box>
                <Box sx={{ fontSize: 14, color: rule.task_available ? ds.text : ds.textMuted, overflowWrap: 'anywhere' }}>
                  → {rule.task_title ?? t('trackingRules.taskDeleted')}
                </Box>
                {!rule.task_available && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: 12, color: ds.warnText }}>
                    <WarningTriangleIcon size={14} />
                    {t('trackingRules.taskUnavailable')}
                  </Box>
                )}
              </ButtonBase>
              <IconButton
                size="small" aria-label={t('trackingRules.delete')}
                onClick={() => setDeleteTarget(rule)} sx={{ color: ds.textMuted, flexShrink: 0 }}
              >
                <TrashIcon size={16} />
              </IconButton>
            </Box>
          ))}
        </Box>
      )}

      {/* 作る・直す */}
      <Dialog open={dialogOpen} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>
          {editing ? t('trackingRules.editTitle') : t('trackingRules.newTitle')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '18px', pt: '8px !important' }}>
          {save.isError && <Alert severity="error">{t('trackingRules.saveError')}</Alert>}
          <TextField
            fullWidth size="small" label={t('trackingRules.app')} helperText={t('trackingRules.appHelp')}
            value={form.app} onChange={(e) => setForm({ ...form, app: e.target.value })}
            error={problem === 'everythingElseExists'}
            slotProps={{ htmlInput: { maxLength: 260, 'data-testid': 'tracking-rule-app' } }}
          />
          <TextField
            fullWidth size="small" label={t('trackingRules.title')} helperText={t('trackingRules.titleHelp')}
            value={form.titleContains} onChange={(e) => setForm({ ...form, titleContains: e.target.value })}
            error={problem === 'everythingElseExists'}
            slotProps={{ htmlInput: { maxLength: 200, 'data-testid': 'tracking-rule-title' } }}
          />
          <TaskPickerField
            label={t('trackingRules.task')} tasks={openTasks} projects={projects ?? []}
            value={form.taskId} onChange={(taskId) => setForm({ ...form, taskId })}
          />
          {formIsEverythingElse(form) && !problem && (
            <Alert severity="info">{t('trackingRules.everythingElseHint')}</Alert>
          )}
          {problem && (
            <Alert severity="warning">
              {t(problem === 'everythingElseExists' ? 'trackingRules.everythingElseExists' : 'trackingRules.needsTask')}
            </Alert>
          )}
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={closeDialog} sx={{ color: ds.textSub }}>{t('trackingRules.cancel')}</Button>
          <Button variant="contained" onClick={submit} disabled={save.isPending} sx={{ px: '24px' }}>
            {t('trackingRules.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 消す */}
      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('trackingRules.deleteTitle')}</DialogTitle>
        <DialogContent>
          {remove.isError && <Alert severity="error" sx={{ mb: '12px' }}>{t('trackingRules.saveError')}</Alert>}
          <Box sx={{ fontSize: 14, color: ds.textSub, overflowWrap: 'anywhere' }}>
            {deleteTarget && t('trackingRules.deleteConfirm', { condition: conditionOf(deleteTarget) })}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDeleteTarget(null)} sx={{ color: ds.textSub }}>{t('trackingRules.cancel')}</Button>
          <Button
            variant="contained" color="error" disabled={remove.isPending}
            onClick={() => deleteTarget && remove.mutate(deleteTarget.id)} sx={{ px: '24px' }}
          >
            {t('trackingRules.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default TrackingRulesPage;
