import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TextField,
} from '@mui/material';
import { getMilestones, createMilestone, updateMilestone, deleteMilestone } from '../api/milestones';
import type { Milestone } from '../types';
import { formatDate } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { PlusIcon, TrashIcon } from '../components/icons';

interface FormData {
  name: string;
  due_date: string;
  description: string;
}

const emptyForm: FormData = { name: '', due_date: '', description: '' };

const toForm = (m: Milestone): FormData => ({
  name: m.name,
  due_date: m.due_date ?? '',
  description: m.description ?? '',
});

const MilestonesPage: React.FC = () => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Milestone | null>(null);
  const [form, setForm] = useState<FormData>(emptyForm);
  const [showNameError, setShowNameError] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Milestone | null>(null);

  useEffect(() => {
    if (!dialogOpen) return;
    setForm(editing ? toForm(editing) : emptyForm);
    setShowNameError(false);
  }, [dialogOpen, editing]);

  const invalidate = () => qc.invalidateQueries({ queryKey: ['milestones'] });

  const save = useMutation({
    mutationFn: (payload: Partial<Milestone>) =>
      editing ? updateMilestone(editing.id, payload) : createMilestone(payload),
    onSuccess: () => { invalidate(); setDialogOpen(false); setEditing(null); },
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteMilestone(id),
    onSuccess: () => { invalidate(); setDeleteTarget(null); },
  });

  const openNew = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (m: Milestone) => { setEditing(m); setDialogOpen(true); };

  const handleSubmit = () => {
    if (!form.name.trim()) { setShowNameError(true); return; }
    save.mutate({
      name: form.name.trim(),
      due_date: form.due_date || null,
      description: form.description.trim() || null,
    });
  };

  const nameError = showNameError && !form.name.trim();

  return (
    <Box sx={{ maxWidth: 720 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: '14px' }}>
        <Box sx={{ fontSize: 13, color: ds.textSub }}>
          {t('taskList.count', { count: data?.length ?? 0 })}
        </Box>
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" startIcon={<PlusIcon size={16} />} onClick={openNew} sx={{ px: '18px' }}>
          {t('milestone.new')}
        </Button>
      </Box>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>}
      {error && <Alert severity="error">{t('common.loadError')}</Alert>}

      {data && (
        <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}>
          <TableContainer>
            <Table size="small" sx={{ '& td': { py: '10px' } }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ minWidth: 200 }}>{t('milestone.name')}</TableCell>
                  <TableCell sx={{ minWidth: 120 }}>{t('milestone.dueDate')}</TableCell>
                  <TableCell>{t('milestone.description')}</TableCell>
                  <TableCell align="right"></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[...data]
                  .sort((a, b) => (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999'))
                  .map((m) => (
                    <TableRow key={m.id} hover sx={{ cursor: 'pointer' }} onClick={() => openEdit(m)}>
                      <TableCell sx={{ fontSize: 13, fontWeight: 500, color: ds.text }}>{m.name}</TableCell>
                      <TableCell sx={{ fontSize: 13, color: ds.textSub }}>
                        {m.due_date ? formatDate(m.due_date) : t('common.dueNone')}
                      </TableCell>
                      <TableCell sx={{
                        fontSize: 13, color: ds.textSub, maxWidth: 260,
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {m.description ?? '—'}
                      </TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          onClick={(e) => { e.stopPropagation(); setDeleteTarget(m); }}
                          sx={{ color: ds.textMuted }}
                        >
                          <TrashIcon size={16} />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                {data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} sx={{ textAlign: 'center', py: '32px', color: ds.textMuted, fontSize: 13 }}>
                      {t('milestone.empty')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {/* 登録・編集ダイアログ */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>
          {editing ? t('milestone.editTitle') : t('milestone.newTitle')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '18px', pt: '8px !important' }}>
          {save.isError && <Alert severity="error">{t('milestone.saveError')}</Alert>}
          <TextField
            autoFocus fullWidth size="small" label={t('milestone.name')}
            value={form.name}
            error={nameError}
            helperText={nameError ? t('milestone.nameRequired') : undefined}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextField
            fullWidth size="small" type="date" label={t('milestone.dueDate')}
            slotProps={{ inputLabel: { shrink: true } }}
            value={form.due_date}
            onChange={(e) => setForm({ ...form, due_date: e.target.value })}
          />
          <TextField
            fullWidth multiline rows={4} size="small" label={t('milestone.description')}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDialogOpen(false)} sx={{ color: ds.textSub }}>
            {t('milestone.cancel')}
          </Button>
          <Button variant="contained" onClick={handleSubmit} disabled={save.isPending} sx={{ px: '24px' }}>
            {t('milestone.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 削除確認ダイアログ */}
      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('milestone.deleteTitle')}</DialogTitle>
        <DialogContent>
          {remove.isError && <Alert severity="error" sx={{ mb: '12px' }}>{t('milestone.deleteError')}</Alert>}
          <Box sx={{ fontSize: 14, color: ds.textSub }}>
            {t('milestone.deleteConfirm', { name: deleteTarget?.name ?? '' })}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDeleteTarget(null)} sx={{ color: ds.textSub }}>
            {t('milestone.cancel')}
          </Button>
          <Button
            variant="contained" color="error" disabled={remove.isPending}
            onClick={() => deleteTarget && remove.mutate(deleteTarget.id)}
            sx={{ px: '24px' }}
          >
            {t('milestone.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MilestonesPage;
