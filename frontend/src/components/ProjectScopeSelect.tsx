// サイドバーの「表示するプロジェクト」（task #187、ADR-0024）。タスク・ガント・カレンダーの期限・
// 実績・マイルストーンが、選んだプロジェクト（と子孫）に絞られる。
import React from 'react';
import { Box, MenuItem, TextField } from '@mui/material';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { pickableProjects, type ProjectScope } from '../projects/projectScope';
import { useProjectScope } from '../projects/useProjectScope';

const ProjectScopeSelect: React.FC = () => {
  const { t } = useI18n();
  const { scope, setScope, projects } = useProjectScope();
  const options = pickableProjects(projects, typeof scope === 'number' ? scope : null);

  return (
    <Box sx={{ px: '18px', pb: '10px' }}>
      <TextField
        select fullWidth size="small"
        label={t('scope.label')}
        value={String(scope)}
        onChange={(e) => {
          const v = e.target.value;
          setScope((v === 'all' || v === 'none' ? v : Number(v)) as ProjectScope);
        }}
        sx={{ '& .MuiInputBase-input': { fontSize: 13 } }}
      >
        <MenuItem value="all" sx={{ fontSize: 13 }}>{t('scope.all')}</MenuItem>
        <MenuItem value="none" sx={{ fontSize: 13 }}>{t('scope.none')}</MenuItem>
        {options.map(({ project, depth }) => (
          <MenuItem key={project.id} value={String(project.id)} sx={{ fontSize: 13, pl: `${16 + depth * 14}px` }}>
            <Box component="span" sx={{
              width: 8, height: 8, borderRadius: '50%', mr: '8px', flexShrink: 0,
              bgcolor: project.color ?? ds.textMuted,
            }} />
            {project.name}
          </MenuItem>
        ))}
      </TextField>
    </Box>
  );
};

export default ProjectScopeSelect;
