// タスクの選び方（task #189、ADR-0026）。締めの画面で打刻に振るときと、上部の打刻ボタンの両方で使う。
// 検索欄と、先頭の候補・プロジェクトの道筋ごとの束・未分類を並べた一覧。並べ方は projects/taskPicker。
import React, { useMemo, useState } from 'react';
import {
  Box, CircularProgress, List, ListItemButton, ListItemText, ListSubheader, TextField,
} from '@mui/material';
import { useI18n } from '../i18n';
import type { Project, Task } from '../types';
import type { ProjectScope } from '../projects/projectScope';
import type { PickerHead, PickerTask } from '../projects/taskPicker';
import { buildTaskPicker } from '../projects/taskPicker';
import { ds } from '../theme';

interface Props {
  tasks: readonly Task[];
  projects: readonly Project[];
  head?: readonly PickerHead[];
  scope?: ProjectScope;
  /** いま付いているタスク（目立たせる） */
  selectedTaskId?: number | null;
  onChoose: (taskId: number) => void;
  loading?: boolean;
  /** 一覧の高さ（外側の器が決めるなら省く） */
  maxHeight?: number | string;
  autoFocus?: boolean;
  /** 検索欄の上に置く行（打刻ボタンの「タスクなし」など） */
  before?: React.ReactNode;
}

const subheader = {
  lineHeight: '30px', fontSize: 12, fontWeight: 700, color: ds.textSub, bgcolor: ds.paper,
  display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0,
} as const;

const TaskPicker: React.FC<Props> = ({
  tasks, projects, head, scope = 'all', selectedTaskId = null, onChoose, loading = false, maxHeight, autoFocus = false, before,
}) => {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const model = useMemo(
    () => buildTaskPicker({ tasks, projects, head, scope, query }),
    [tasks, projects, head, scope, query],
  );
  const firstOutside = scope === 'all' ? -1 : model.groups.findIndex((g) => !g.inScope);
  const hasOpenTasks = tasks.length > 0;

  const item = (task: PickerTask, secondary: string | null) => (
    <ListItemButton
      key={task.taskId}
      selected={selectedTaskId === task.taskId}
      onClick={() => onChoose(task.taskId)}
      sx={{ minHeight: 44, pl: task.reason ? '16px' : '28px' }}
      data-testid={`pick-task-${task.taskId}`}
    >
      <ListItemText
        primary={task.title}
        secondary={secondary}
        slotProps={{
          primary: { sx: { fontSize: 14, overflowWrap: 'anywhere' } },
          secondary: { sx: { fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
        }}
      />
    </ListItemButton>
  );
  const reasonText = (task: PickerTask) => {
    const reason = task.reason === 'schedule' ? t('picker.reasonSchedule') : t('picker.reasonRecent');
    return `${reason} ・ ${task.projectPath ?? t('picker.unclassified')}`;
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: '1 1 auto' }}>
      {before}
      <Box sx={{ p: '10px 12px 6px' }}>
        <TextField
          autoFocus={autoFocus} size="small" fullWidth value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder={t('picker.search')}
          // メニューの中で文字を打っても、頭文字で項目へ飛ぶ既定の動きに取られないように
          onKeyDown={(e) => e.stopPropagation()}
          slotProps={{ htmlInput: { 'aria-label': t('picker.search'), 'data-testid': 'task-picker-search' } }}
        />
      </Box>
      <List dense sx={{ maxHeight, overflowY: 'auto', pt: 0, flex: '1 1 auto', minHeight: 0 }} data-testid="task-picker-list">
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: '12px' }}><CircularProgress size={18} /></Box>
        )}
        {model.head.length > 0 && (
          <li>
            <ul style={{ padding: 0 }}>
              <ListSubheader sx={subheader}>{t('picker.head')}</ListSubheader>
              {model.head.map((task) => item(task, reasonText(task)))}
            </ul>
          </li>
        )}
        {model.groups.map((group, i) => (
          <li key={group.key}>
            <ul style={{ padding: 0 }}>
              {i === firstOutside && (
                <Box sx={{
                  px: '16px', pt: '10px', pb: '2px', fontSize: 11, color: ds.textMuted, borderTop: `1px solid ${ds.borderFaint}`,
                }}>
                  {t('picker.outsideScope')}
                </Box>
              )}
              <ListSubheader sx={{ ...subheader, color: group.inScope ? ds.textSub : ds.textMuted }} title={group.label ?? undefined}>
                <Box component="span" sx={{
                  width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                  bgcolor: group.projectId === null ? 'transparent' : group.color ?? ds.todoGray,
                  border: group.projectId === null ? `1px dashed ${ds.textMuted}` : 'none',
                }} />
                <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {group.label ?? t('picker.unclassified')}
                </Box>
              </ListSubheader>
              {group.tasks.map((task) => item(task, null))}
            </ul>
          </li>
        ))}
        {!loading && model.empty && (
          <Box sx={{ px: '16px', py: '10px', fontSize: 13, color: ds.textMuted }}>
            {hasOpenTasks || query ? t('picker.none') : t('picker.noTasks')}
          </Box>
        )}
      </List>
    </Box>
  );
};

export default TaskPicker;
