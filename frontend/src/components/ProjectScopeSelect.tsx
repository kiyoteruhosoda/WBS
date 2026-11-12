// The sidebar's "displayed project" (task #187, ADR-0024). Tasks, Gantt, calendar due dates,
// actuals and milestones are filtered to the selected project (and its descendants). The same control is also placed above the task list
// (`inline`. There is one state, so changing either one updates the other. ADR-0030).
import React from 'react';
import { Box, MenuItem, TextField } from '@mui/material';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { pickableProjects, type ProjectScope } from '../projects/projectScope';
import { useProjectScope } from '../projects/useProjectScope';

interface Props {
  /** Placed in the task list toolbar (no margin, fixed width) */
  inline?: boolean;
}

const ProjectScopeSelect: React.FC<Props> = ({ inline = false }) => {
  const { t } = useI18n();
  const { scope, setScope, projects } = useProjectScope();
  const options = pickableProjects(projects, typeof scope === 'number' ? scope : null);
  // Above the list, show the full path (a bare name like "Design" doesn't tell which project it belongs to)
  const pathOf = (v: unknown): string => {
    if (v === 'all') return t('scope.all');
    if (v === 'none') return t('scope.none');
    return projects.find((p) => String(p.id) === v)?.path ?? '';
  };

  return (
    <Box sx={inline ? { minWidth: 180, maxWidth: { xs: '100%', sm: 280 }, flex: { xs: '1 1 100%', sm: '0 1 auto' } } : { px: '18px', pb: '10px' }}>
      <TextField
        select fullWidth size="small"
        label={inline ? t('taskList.project') : t('scope.label')}
        data-testid={inline ? 'tasklist-project-filter' : undefined}
        slotProps={inline ? { select: { renderValue: pathOf } } : undefined}
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
