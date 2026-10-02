// フォームの中のタスクの欄（task #189、ADR-0026）。予定の編集画面の「結ぶタスク」で使う。
// 並べ方・束ね方・検索は打刻ボタン・締めの画面の TaskPicker と同じ（projects/taskPicker）で、
// 見せ方だけ入力欄（Autocomplete）にしたもの。選んだ後は欄の下に道筋を出す（同じ名前のタスクを取り違えない）。
import React, { useMemo } from 'react';
import { Autocomplete, Box, ListSubheader, TextField } from '@mui/material';
import { useI18n } from '../i18n';
import type { Project, Task } from '../types';
import type { ProjectScope } from '../projects/projectScope';
import type { PickerTask } from '../projects/taskPicker';
import { buildTaskPicker, flattenPicker, matchesQuery } from '../projects/taskPicker';
import { ds } from '../theme';

interface Props {
  label: string;
  tasks: readonly Task[];
  projects: readonly Project[];
  scope?: ProjectScope;
  value: number | null;
  onChange: (taskId: number | null) => void;
}

interface Option {
  task: PickerTask;
  groupKey: string;
}

const TaskPickerField: React.FC<Props> = ({ label, tasks, projects, scope = 'all', value, onChange }) => {
  const { t } = useI18n();
  // 検索は Autocomplete の入力で絞る（束ね方は検索語に依らないので、ここでは語なしで組む）
  const model = useMemo(
    () => buildTaskPicker({ tasks, projects, scope, keep: value }),
    [tasks, projects, scope, value],
  );
  const options = useMemo<Option[]>(() => flattenPicker(model), [model]);
  const groups = useMemo(() => new Map(model.groups.map((g) => [g.key, g])), [model]);
  const firstOutside = scope === 'all' ? null : model.groups.find((g) => !g.inScope)?.key ?? null;
  const selected = options.find((o) => o.task.taskId === value) ?? null;

  return (
    <Autocomplete
      options={options}
      value={selected}
      onChange={(_, option) => onChange(option?.task.taskId ?? null)}
      getOptionLabel={(option) => option.task.title}
      isOptionEqualToValue={(a, b) => a.task.taskId === b.task.taskId}
      groupBy={(option) => option.groupKey}
      filterOptions={(list, state) => list.filter((o) => matchesQuery(o.task.title, o.task.projectPath, state.inputValue))}
      renderGroup={(params) => {
        const group = groups.get(params.group);
        return (
          <li key={params.key}>
            {params.group === firstOutside && (
              <Box sx={{ px: '16px', pt: '10px', pb: '2px', fontSize: 11, color: ds.textMuted, borderTop: `1px solid ${ds.borderFaint}` }}>
                {t('picker.outsideScope')}
              </Box>
            )}
            <ListSubheader component="div" sx={{
              lineHeight: '30px', fontSize: 12, fontWeight: 700, color: group?.inScope === false ? ds.textMuted : ds.textSub,
              display: 'flex', alignItems: 'center', gap: '6px',
            }}>
              {group && (
                <Box component="span" sx={{
                  width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                  bgcolor: group.projectId === null ? 'transparent' : group.color ?? ds.todoGray,
                  border: group.projectId === null ? `1px dashed ${ds.textMuted}` : 'none',
                }} />
              )}
              <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {group ? group.label ?? t('picker.unclassified') : t('picker.head')}
              </Box>
            </ListSubheader>
            <ul style={{ padding: 0 }}>{params.children}</ul>
          </li>
        );
      }}
      renderOption={({ key, ...props }, option) => (
        <li key={key} {...props} style={{ paddingLeft: 28, minHeight: 40 }}>{option.task.title}</li>
      )}
      noOptionsText={t('picker.none')}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={t('picker.search')}
          helperText={selected ? selected.task.projectPath ?? t('picker.unclassified') : undefined}
        />
      )}
    />
  );
};

export default TaskPickerField;
