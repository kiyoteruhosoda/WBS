import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TextField,
} from '@mui/material';
import { getCategories, createCategory, updateCategory, deleteCategory } from '../api/categories';
import type { Category } from '../types';
import { useI18n } from '../i18n';
import { ds, categoryColor, categoryPalette } from '../theme';
import { PlusIcon, TrashIcon } from '../components/icons';

interface FormData {
  name: string;
  color: string | null;
  sort_order: string;
}

const emptyForm: FormData = { name: '', color: null, sort_order: '0' };

const toForm = (c: Category): FormData => ({
  name: c.name,
  color: c.color ?? null,
  sort_order: String(c.sort_order ?? 0),
});

const CategoriesPage: React.FC = () => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);
  const [form, setForm] = useState<FormData>(emptyForm);
  const [showNameError, setShowNameError] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null);

  useEffect(() => {
    if (!dialogOpen) return;
    setForm(editing ? toForm(editing) : emptyForm);
    setShowNameError(false);
  }, [dialogOpen, editing]);

  const invalidate = () => qc.invalidateQueries({ queryKey: ['categories'] });

  const save = useMutation({
    mutationFn: (payload: Partial<Category>) =>
      editing ? updateCategory(editing.id, payload) : createCategory(payload),
    onSuccess: () => { invalidate(); setDialogOpen(false); setEditing(null); },
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteCategory(id),
    onSuccess: () => { invalidate(); setDeleteTarget(null); },
  });

  const openNew = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (c: Category) => { setEditing(c); setDialogOpen(true); };

  const handleSubmit = () => {
    if (!form.name.trim()) { setShowNameError(true); return; }
    const parsedOrder = Number(form.sort_order);
    save.mutate({
      name: form.name.trim(),
      color: form.color,
      sort_order: Number.isFinite(parsedOrder) ? parsedOrder : 0,
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
          {t('category.new')}
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
                  <TableCell sx={{ minWidth: 240 }}>{t('category.name')}</TableCell>
                  <TableCell>{t('category.color')}</TableCell>
                  <TableCell>{t('category.sortOrder')}</TableCell>
                  <TableCell align="right"></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[...data].sort((a, b) => a.sort_order - b.sort_order).map((c) => (
                  <TableRow key={c.id} hover sx={{ cursor: 'pointer' }} onClick={() => openEdit(c)}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <Box sx={{
                          width: 12, height: 12, borderRadius: '50%', flexShrink: 0,
                          bgcolor: categoryColor(c.id, c.color),
                        }} />
                        <Box sx={{ fontSize: 13, fontWeight: 500, color: ds.text }}>{c.name}</Box>
                      </Box>
                    </TableCell>
                    <TableCell sx={{ fontSize: 13, color: ds.textSub, fontFamily: 'ui-monospace, monospace' }}>
                      {c.color ?? '—'}
                    </TableCell>
                    <TableCell sx={{ fontSize: 13, color: ds.textSub }}>{c.sort_order}</TableCell>
                    <TableCell align="right">
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(c); }}
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
                      {t('category.empty')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {/* 登録・編集ダイアログ */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>
          {editing ? t('category.editTitle') : t('category.newTitle')}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: '18px', pt: '8px !important' }}>
          {save.isError && <Alert severity="error">{t('category.saveError')}</Alert>}
          <TextField
            autoFocus fullWidth size="small" label={t('category.name')}
            value={form.name}
            error={nameError}
            helperText={nameError ? t('category.nameRequired') : undefined}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Box>
            <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text, mb: '8px' }}>{t('category.color')}</Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              {categoryPalette.map((color) => {
                const selected = form.color === color;
                return (
                  <Box
                    key={color}
                    component="button"
                    type="button"
                    onClick={() => setForm({ ...form, color })}
                    aria-label={color}
                    sx={{
                      width: 26, height: 26, borderRadius: '50%', cursor: 'pointer', p: 0,
                      bgcolor: color,
                      border: selected ? `2px solid ${ds.text}` : `1px solid ${ds.border}`,
                      outline: selected ? `2px solid ${ds.paper}` : 'none',
                      outlineOffset: '-4px',
                    }}
                  />
                );
              })}
              <Box
                component="button"
                type="button"
                onClick={() => setForm({ ...form, color: null })}
                sx={{
                  height: 26, px: '10px', borderRadius: '13px', cursor: 'pointer', fontSize: 12,
                  bgcolor: form.color === null ? ds.primaryPale : ds.paper,
                  color: form.color === null ? ds.primary : ds.textSub,
                  border: form.color === null ? `1.5px solid ${ds.primary}` : `1px solid ${ds.border}`,
                }}
              >
                {t('category.noColor')}
              </Box>
              <TextField
                size="small" type="color" aria-label={t('category.customColor')}
                value={form.color ?? '#0017C1'}
                onChange={(e) => setForm({ ...form, color: e.target.value })}
                sx={{ width: 52, '& input': { p: '4px', height: 26, cursor: 'pointer' } }}
              />
            </Box>
          </Box>
          <TextField
            fullWidth size="small" type="number" label={t('category.sortOrder')}
            helperText={t('category.sortOrderHelp')}
            slotProps={{ htmlInput: { step: 1 } }}
            value={form.sort_order}
            onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
          />
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDialogOpen(false)} sx={{ color: ds.textSub }}>
            {t('category.cancel')}
          </Button>
          <Button variant="contained" onClick={handleSubmit} disabled={save.isPending} sx={{ px: '24px' }}>
            {t('category.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 削除確認ダイアログ */}
      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('category.deleteTitle')}</DialogTitle>
        <DialogContent>
          {remove.isError && <Alert severity="error" sx={{ mb: '12px' }}>{t('category.deleteError')}</Alert>}
          <Box sx={{ fontSize: 14, color: ds.textSub }}>
            {t('category.deleteConfirm', { name: deleteTarget?.name ?? '' })}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button onClick={() => setDeleteTarget(null)} sx={{ color: ds.textSub }}>
            {t('category.cancel')}
          </Button>
          <Button
            variant="contained" color="error" disabled={remove.isPending}
            onClick={() => deleteTarget && remove.mutate(deleteTarget.id)}
            sx={{ px: '24px' }}
          >
            {t('category.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CategoriesPage;
