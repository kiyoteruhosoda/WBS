// Project list (/projects. task #187, ADR-0024).
// ⚠ Projects nest to any depth, so they hang under their parent instead of being flat table rows (same as nolumiatask's ProjectsPage).
// Moving is done with row actions (up, down, change parent). nolumiatask's tree long-press (ADR-0067) is not brought over
// -- there are only dozens of projects and they rarely move. Row actions also work from the keyboard.
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { isForbidden } from '../api/forbidden';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, IconButton, ListItemText, Menu, MenuItem, Switch, TextField, Tooltip,
} from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { createProject, deleteProject, moveProject, updateProject, PROJECTS_KEY } from '../api/projects';
import { ACTUALS_KEY } from '../api/actuals';
import type { Project } from '../types';
import { useI18n } from '../i18n';
import { ds, categoryPalette } from '../theme';
import { PlusIcon } from '../components/icons';
import {
  flattenTree, isEffectivelyArchived, parentCandidates, toTree, type ProjectNode,
} from '../projects/projectScope';
import { useProjects, useProjectScope } from '../projects/useProjectScope';
import ProjectMembersDialog from '../components/ProjectMembersDialog';
import ProjectCalendarDialog from '../components/ProjectCalendarDialog';
import { useAuth } from '../auth/AuthProvider';

interface FormData {
  name: string;
  parent: string; // '' = top level
  color: string | null;
  code: string;
  description: string;
}

const emptyForm = (parent: number | null): FormData => ({
  name: '', parent: parent === null ? '' : String(parent), color: null, code: '', description: '',
});

const toForm = (p: Project): FormData => ({
  name: p.name,
  parent: p.parent_project_id === null ? '' : String(p.parent_project_id),
  color: p.color,
  code: p.code ?? '',
  description: p.description ?? '',
});

const ColorPicker: React.FC<{ value: string | null; onChange: (v: string | null) => void }> = ({ value, onChange }) => {
  const { t } = useI18n();
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
      {categoryPalette.map((color) => {
        const selected = value === color;
        return (
          <Box
            key={color} component="button" type="button" aria-label={color} aria-pressed={selected}
            onClick={() => onChange(color)}
            sx={{
              width: 26, height: 26, borderRadius: '50%', cursor: 'pointer', p: 0, bgcolor: color,
              border: selected ? `2px solid ${ds.text}` : `1px solid ${ds.border}`,
              outline: selected ? `2px solid ${ds.paper}` : 'none', outlineOffset: '-4px',
            }}
          />
        );
      })}
      <Box
        component="button" type="button" aria-pressed={value === null} onClick={() => onChange(null)}
        sx={{
          height: 26, px: '10px', borderRadius: '13px', cursor: 'pointer', fontSize: 12,
          bgcolor: value === null ? ds.primaryPale : ds.paper,
          color: value === null ? ds.primary : ds.textSub,
          border: value === null ? `1.5px solid ${ds.primary}` : `1px solid ${ds.border}`,
        }}
      >
        {t('category.noColor')}
      </Box>
    </Box>
  );
};

const ProjectsPage: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading, error } = useProjects();
  const { setScope } = useProjectScope();
  const { user, ssoEnabled } = useAuth();
  const projects = useMemo(() => data ?? [], [data]);
  // Only marked users can create top-level projects (ADR-0065). Deployments without SSO have a single user, who can
  const canCreateTop = !ssoEnabled || Boolean(user?.can_create_projects);

  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState<{ editing: Project | null; parent: number | null } | null>(null);
  const [form, setForm] = useState<FormData>(emptyForm(null));
  const [showNameError, setShowNameError] = useState(false);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; node: ProjectNode } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [moveError, setMoveError] = useState<'failed' | 'forbidden' | null>(null);
  // Members dialog (ADR-0055. Shows the root's roster from any level)
  const [membersOf, setMembersOf] = useState<Project | null>(null);
  // Working days and time off (task #554, ADR-0058)
  const [calendarOf, setCalendarOf] = useState<Project | null>(null);

  useEffect(() => {
    if (dialog === null) return;
    setForm(dialog.editing ? toForm(dialog.editing) : emptyForm(dialog.parent));
    setShowNameError(false);
  }, [dialog]);

  const tree = useMemo(() => toTree(projects), [projects]);
  const rows = useMemo(
    () => flattenTree(tree).filter((n) => showArchived || !isEffectivelyArchived(projects, n.project.id)),
    [tree, projects, showArchived],
  );
  const archivedCount = projects.filter((p) => isEffectivelyArchived(projects, p.id)).length;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: PROJECTS_KEY });
    // Paths may have changed, and milestones no longer reachable may have been detached
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['task'] });
    qc.invalidateQueries({ queryKey: ['milestones'] });
    qc.invalidateQueries({ queryKey: ACTUALS_KEY });
  };

  const save = useMutation({
    mutationFn: async () => {
      const parent = form.parent === '' ? null : Number(form.parent);
      const fields = {
        name: form.name.trim(), color: form.color,
        code: form.code.trim() || null, description: form.description.trim() || null,
      };
      const editing = dialog?.editing ?? null;
      if (editing === null) return createProject({ ...fields, parent_project_id: parent });
      const saved = await updateProject(editing.id, fields);
      return parent !== editing.parent_project_id ? moveProject(editing.id, parent) : saved;
    },
    onSuccess: () => { invalidate(); setDialog(null); },
  });

  const move = useMutation({
    mutationFn: ({ id, parent, position }: { id: number; parent: number | null; position: number }) =>
      moveProject(id, parent, position),
    onSuccess: () => { setMoveError(null); invalidate(); },
    onError: (error) => setMoveError(isForbidden(error) ? 'forbidden' : 'failed'),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, archived }: { id: number; archived: boolean }) =>
      updateProject(id, { status: archived ? 'archived' : 'active' }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteProject(id),
    onSuccess: () => { invalidate(); setDeleteTarget(null); },
  });
  const deleteBlocked = isAxiosError(remove.error) && remove.error.response?.status === 409;
  // Only admins can delete top-level projects (ADR-0055)
  const deleteForbidden = isAxiosError(remove.error) && remove.error.response?.status === 403;
  const rootName = (p: Project | null) => (p ? projects.find((x) => x.id === p.root_project_id)?.name ?? p.name : '');

  const siblingsOf = (p: Project): Project[] =>
    flattenTree(tree)
      .map((n) => n.project)
      .filter((x) => x.parent_project_id === p.parent_project_id)
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);

  const handleSubmit = () => {
    if (!form.name.trim()) { setShowNameError(true); return; }
    save.mutate();
  };

  const nameError = showNameError && !form.name.trim();
  const editingId = dialog?.editing?.id ?? null;
  const parentOptions = editingId === null ? flattenTree(tree) : parentCandidates(projects, editingId);

  const openTasks = (p: Project) => { setScope(p.id); navigate('/tasks'); };
  // Default parent for "new project". Users who can't create top-level projects create under the first root they belong to
  const firstRoot = projects.find((p) => p.parent_project_id === null && p.status === 'active') ?? null;
  const newProjectParent = canCreateTop ? null : firstRoot?.id ?? null;

  return (
    <Box sx={{ maxWidth: 820 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '12px', mb: '10px', flexWrap: 'wrap' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>{t('taskList.count', { count: rows.length })}</Box>
        {archivedCount > 0 && (
          <FormControlLabel
            control={<Switch size="small" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />}
            label={<Box sx={{ fontSize: 13, color: ds.textSub }}>{t('project.showArchived')}</Box>}
          />
        )}
        <Box sx={{ flex: 1 }} />
        {(canCreateTop || firstRoot !== null) && (
          <Button variant="contained" startIcon={<PlusIcon size={16} />} onClick={() => setDialog({ editing: null, parent: newProjectParent })} sx={{ px: '18px' }}>
            {t('project.new')}
          </Button>
        )}
      </Box>
      <Box sx={{ fontSize: 13, color: ds.textSub, mb: '14px' }}>{t('project.hint')}</Box>
      {!canCreateTop && <Box sx={{ fontSize: 13, color: ds.textSub, mb: '14px' }}>{t('project.topNeedsCreator')}</Box>}

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}
      {moveError && <Alert severity="error" sx={{ mb: '12px' }} onClose={() => setMoveError(null)}>{moveError === 'forbidden' ? t('move.crossTreeManagerOnly') : t('project.moveError')}</Alert>}

      {data && (
        <Box
          component="ul"
          aria-label={t('nav.projects')}
          sx={{ listStyle: 'none', m: 0, p: 0, bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}
        >
          {rows.map((node) => {
            const p = node.project;
            const archived = isEffectivelyArchived(projects, p.id);
            return (
              <Box
                component="li"
                key={p.id}
                sx={{
                  display: 'flex', alignItems: 'center', gap: '8px', minHeight: 48,
                  pl: `${14 + node.depth * 22}px`, pr: '6px',
                  borderTop: `1px solid ${ds.borderPale}`, '&:first-of-type': { borderTop: 'none' },
                  '&:hover': { bgcolor: ds.hairline },
                }}
              >
                {/* Show depth with lines (indentation alone doesn't tell the level) */}
                {node.depth > 0 && (
                  <Box aria-hidden sx={{ width: 10, height: 1.5, bgcolor: ds.border, flexShrink: 0, ml: '-14px' }} />
                )}
                <Box sx={{ width: 12, height: 12, borderRadius: '50%', flexShrink: 0, bgcolor: p.color ?? ds.border }} />
                <Box
                  component="button" type="button" onClick={() => setDialog({ editing: p, parent: null })}
                  sx={{
                    flex: 1, minWidth: 0, textAlign: 'left', border: 'none', bgcolor: 'transparent', cursor: 'pointer',
                    font: 'inherit', p: '10px 0', color: archived ? ds.textMuted : ds.text,
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <Box sx={{ fontSize: 14, fontWeight: 600, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.name}
                    </Box>
                    {/* Code (optional): a subtle chip next to the name. The chip is kept even when the name is truncated */}
                    {p.code && (
                      <Box
                        component="span"
                        sx={{
                          flexShrink: 0, maxWidth: '45%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 11, lineHeight: '16px',
                          color: ds.textSub, bgcolor: ds.hairline, border: `1px solid ${ds.borderPale}`, borderRadius: '4px', px: '5px',
                        }}
                      >
                        {p.code}
                      </Box>
                    )}
                  </Box>
                  {p.description && (
                    <Box sx={{ fontSize: 12, color: ds.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.description}
                    </Box>
                  )}
                </Box>
                {p.status === 'archived' && <Chip size="small" label={t('project.archived')} sx={{ fontSize: 11 }} />}
                {node.depth === 0 && (
                  <Button size="small" onClick={() => setMembersOf(p)} sx={{ whiteSpace: 'nowrap', display: { xs: 'none', sm: 'inline-flex' } }}>
                    {t('project.members')}
                  </Button>
                )}
                {/* Every level has a calendar (sub-projects inherit the parent's holidays and add their own. ADR-0059) */}
                <Button size="small" onClick={() => setCalendarOf(p)} sx={{ whiteSpace: 'nowrap', display: { xs: 'none', sm: 'inline-flex' } }}>
                  {t('project.teamCalendar')}
                </Button>
                <Button size="small" onClick={() => openTasks(p)} sx={{ whiteSpace: 'nowrap', display: { xs: 'none', sm: 'inline-flex' } }}>
                  {t('project.openTasks')}
                </Button>
                <Tooltip title={t('project.newChild')}>
                  <IconButton size="small" aria-label={t('project.newChild')} onClick={() => setDialog({ editing: null, parent: p.id })}>
                    <PlusIcon size={16} />
                  </IconButton>
                </Tooltip>
                <IconButton size="small" aria-label={`${t('project.menu')}: ${p.name}`} onClick={(e) => setMenu({ anchor: e.currentTarget, node })}>
                  <MoreVertIcon fontSize="small" />
                </IconButton>
              </Box>
            );
          })}
          {rows.length === 0 && (
            <Box component="li" sx={{ textAlign: 'center', py: '32px', color: ds.textMuted, fontSize: 13 }}>
              {t('project.empty')}
            </Box>
          )}
        </Box>
      )}
      {archivedCount > 0 && showArchived && (
        <Box sx={{ fontSize: 12, color: ds.textMuted, mt: '8px' }}>{t('project.archivedHint')}</Box>
      )}

      {/* Row actions */}
      <Menu anchorEl={menu?.anchor} open={menu !== null} onClose={() => setMenu(null)}>
        {menu && (() => {
          const p = menu.node.project;
          const siblings = siblingsOf(p);
          const index = siblings.findIndex((s) => s.id === p.id);
          const close = (fn: () => void) => () => { setMenu(null); fn(); };
          return [
            <MenuItem key="edit" onClick={close(() => setDialog({ editing: p, parent: null }))}>
              <ListItemText>{t('project.editTitle')}</ListItemText>
            </MenuItem>,
            <MenuItem key="tasks" onClick={close(() => openTasks(p))}>
              <ListItemText>{t('project.openTasks')}</ListItemText>
            </MenuItem>,
            <MenuItem key="members" onClick={close(() => setMembersOf(p))}>
              <ListItemText>{t('project.members')}</ListItemText>
            </MenuItem>,
            <MenuItem key="calendar" onClick={close(() => setCalendarOf(p))}>
              <ListItemText>{t('project.teamCalendar')}</ListItemText>
            </MenuItem>,
            <MenuItem key="up" disabled={index <= 0}
              onClick={close(() => move.mutate({ id: p.id, parent: p.parent_project_id, position: index - 1 }))}>
              <ListItemText>{t('project.moveUp')}</ListItemText>
            </MenuItem>,
            <MenuItem key="down" disabled={index < 0 || index >= siblings.length - 1}
              onClick={close(() => move.mutate({ id: p.id, parent: p.parent_project_id, position: index + 1 }))}>
              <ListItemText>{t('project.moveDown')}</ListItemText>
            </MenuItem>,
            <MenuItem key="archive" onClick={close(() => setStatus.mutate({ id: p.id, archived: p.status !== 'archived' }))}>
              <ListItemText>{p.status === 'archived' ? t('project.restore') : t('project.archive')}</ListItemText>
            </MenuItem>,
            <MenuItem key="delete" onClick={close(() => { remove.reset(); setDeleteTarget(p); })} sx={{ color: ds.danger }}>
              <ListItemText>{t('project.delete')}</ListItemText>
            </MenuItem>,
          ];
        })()}
      </Menu>

      {/* Create / edit */}
      <Dialog open={dialog !== null} onClose={() => setDialog(null)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>
          {dialog?.editing ? t('project.editTitle') : t('project.newTitle')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '18px', pt: '8px !important' }}>
          {save.isError && <Alert severity="error">{isForbidden(save.error) ? t('move.crossTreeManagerOnly') : t('project.saveError')}</Alert>}
          <TextField
            autoFocus fullWidth size="small" label={t('project.name')} value={form.name}
            error={nameError} helperText={nameError ? t('project.nameRequired') : undefined}
            slotProps={{ htmlInput: { maxLength: 200 } }}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextField
            fullWidth size="small" label={t('project.code')} value={form.code} helperText={t('project.codeHint')}
            slotProps={{ htmlInput: { maxLength: 32, spellCheck: false, autoCapitalize: 'off' } }}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
          />
          <TextField
            select fullWidth size="small" label={t('project.parent')} value={form.parent}
            onChange={(e) => setForm({ ...form, parent: e.target.value })}
          >
            {/* Anyone can promote a sub-project to a root (members are copied over). Only marked users can create a new root */}
            <MenuItem value="" disabled={editingId === null && !canCreateTop}>{t('project.noParent')}</MenuItem>
            {parentOptions.map(({ project, depth }) => (
              <MenuItem key={project.id} value={String(project.id)} sx={{ pl: `${16 + depth * 14}px` }}>
                {project.name}
              </MenuItem>
            ))}
          </TextField>
          <Box>
            <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text, mb: '8px' }}>{t('project.color')}</Box>
            <ColorPicker value={form.color} onChange={(color) => setForm({ ...form, color })} />
          </Box>
          <TextField
            fullWidth size="small" multiline minRows={2} label={t('project.description')} value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDialog(null)} sx={{ color: ds.textSub }}>{t('project.cancel')}</Button>
          <Button variant="contained" onClick={handleSubmit} disabled={save.isPending} sx={{ px: '24px' }}>
            {t('project.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <ProjectMembersDialog project={membersOf} rootName={rootName(membersOf)} onClose={() => setMembersOf(null)} />
      <ProjectCalendarDialog project={calendarOf} rootName={rootName(calendarOf)} onClose={() => setCalendarOf(null)} />

      {/* Delete (empty projects only; refused when not empty) */}
      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('project.deleteTitle')}</DialogTitle>
        <DialogContent>
          {remove.isError && (
            <Alert severity={deleteBlocked ? 'warning' : 'error'} sx={{ mb: '12px' }}>
              {deleteBlocked
                ? t('project.deleteNotEmpty')
                : deleteForbidden ? t('project.deleteManagerOnly') : t('project.deleteError')}
            </Alert>
          )}
          <Box sx={{ fontSize: 14, color: ds.textSub }}>
            {t('project.deleteConfirm', { name: deleteTarget?.path ?? '' })}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDeleteTarget(null)} sx={{ color: ds.textSub }}>{t('project.cancel')}</Button>
          {deleteBlocked && deleteTarget && deleteTarget.status !== 'archived' ? (
            <Button
              variant="contained"
              onClick={() => { setStatus.mutate({ id: deleteTarget.id, archived: true }); setDeleteTarget(null); }}
              sx={{ px: '24px' }}
            >
              {t('project.archive')}
            </Button>
          ) : (
            <Button
              variant="contained" color="error" disabled={remove.isPending || deleteBlocked}
              onClick={() => deleteTarget && remove.mutate(deleteTarget.id)} sx={{ px: '24px' }}
            >
              {t('project.delete')}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ProjectsPage;
