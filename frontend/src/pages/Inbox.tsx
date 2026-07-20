import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, CircularProgress, Alert, TextField, Button, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, InputLabel, Select, MenuItem,
} from '@mui/material';
import { getInbox, createInboxItem, convertInboxItem, deleteInboxItem } from '../api/inbox';
import { getCategories } from '../api/categories';

import { formatDate } from '../utils/format';
import { useI18n } from '../i18n';
import { ds } from '../theme';
import { PlusIcon, TrashIcon, SwapIcon } from '../components/icons';

const Inbox: React.FC = () => {
  const qc = useQueryClient();
  const { t } = useI18n();
  const [title, setTitle] = useState('');
  const [memo, setMemo] = useState('');
  const [convertId, setConvertId] = useState<number | null>(null);
  const [convTitle, setConvTitle] = useState('');
  const [convDue, setConvDue] = useState('');
  const [convCat, setConvCat] = useState('');

  const { data, isLoading, error } = useQuery({ queryKey: ['inbox'], queryFn: getInbox });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const add = useMutation({
    mutationFn: () => createInboxItem({ title, memo: memo || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inbox'] }); setTitle(''); setMemo(''); },
  });

  const del = useMutation({
    mutationFn: (id: number) => deleteInboxItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inbox'] }),
  });

  const convert = useMutation({
    mutationFn: () => convertInboxItem(convertId!, {
      title: convTitle,
      due_date: convDue || null, category_id: convCat ? Number(convCat) : null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inbox'] });
      qc.invalidateQueries({ queryKey: ['tasks'] });
      setConvertId(null);
    },
  });

  const openConvert = (id: number, itemTitle: string) => {
    setConvertId(id); setConvTitle(itemTitle); setConvDue(''); setConvCat('');
  };

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">{t('common.loadError')}</Alert>;

  return (
    <Box sx={{ maxWidth: 720 }}>
      {/* クイック追加 */}
      <Box sx={{
        display: 'flex', gap: '10px', mb: '20px', flexWrap: 'wrap',
        bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', p: '14px',
      }}>
        <TextField size="small" placeholder={t('inbox.titlePlaceholder')} value={title}
          onChange={e => setTitle(e.target.value)} sx={{ flex: 1, minWidth: 200 }} />
        <TextField size="small" placeholder={t('inbox.memoPlaceholder')} value={memo}
          onChange={e => setMemo(e.target.value)} sx={{ flex: 1, minWidth: 160 }} />
        <Button variant="contained" startIcon={<PlusIcon size={14} />} onClick={() => add.mutate()} disabled={!title}>
          {t('inbox.add')}
        </Button>
      </Box>

      <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}>
        {data?.length === 0 && (
          <Box sx={{ px: '18px', py: '24px', fontSize: 13, color: ds.textMuted, textAlign: 'center' }}>
            {t('inbox.empty')}
          </Box>
        )}
        {data?.map(item => (
          <Box key={item.id} sx={{
            display: 'flex', alignItems: 'center', gap: '12px', px: '16px', py: '12px',
            borderBottom: `1px solid ${ds.hairline}`, '&:last-child': { borderBottom: 'none' },
            '&:hover': { bgcolor: '#FAFAFA' },
          }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box sx={{ fontSize: 14, fontWeight: 500, color: ds.text }}>{item.title}</Box>
              <Box sx={{ fontSize: 12, color: ds.textMuted, mt: '2px' }}>
                {formatDate(item.created_at)}
                {item.memo ? ` ・ ${item.memo}` : ''}
              </Box>
            </Box>
            {item.converted_task_id ? (
              <Box sx={{
                px: '10px', py: '2px', borderRadius: '10px', fontSize: 11, fontWeight: 700,
                bgcolor: ds.successPale, color: ds.successDark, whiteSpace: 'nowrap',
              }}>
                {t('inbox.converted')}
              </Box>
            ) : (
              <IconButton size="small" title={t('inbox.convertToTask')} onClick={() => openConvert(item.id, item.title)} sx={{ color: ds.primary }}>
                <SwapIcon size={18} />
              </IconButton>
            )}
            <IconButton size="small" onClick={() => del.mutate(item.id)} sx={{ color: ds.textMuted }}>
              <TrashIcon size={18} />
            </IconButton>
          </Box>
        ))}
      </Box>

      <Dialog open={convertId !== null} onClose={() => setConvertId(null)} maxWidth="sm" fullWidth
        slotProps={{ paper: { sx: { borderRadius: '10px' } } }}>
        <DialogTitle sx={{ fontSize: 16, fontWeight: 700 }}>{t('inbox.convertToTask')}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: '16px', mt: '8px' }}>
            <TextField label={t('inbox.taskName')} value={convTitle} onChange={e => setConvTitle(e.target.value)} fullWidth size="small" />
            <TextField type="date" label={t('inbox.dueDate')} slotProps={{ inputLabel: { shrink: true } }}
              value={convDue} onChange={e => setConvDue(e.target.value)} fullWidth size="small" />
            <FormControl fullWidth size="small">
              <InputLabel>{t('inbox.category')}</InputLabel>
              <Select value={convCat} label={t('inbox.category')} onChange={e => setConvCat(e.target.value)}>
                <MenuItem value="">{t('inbox.none')}</MenuItem>
                {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: '24px', pb: '18px' }}>
          <Button
            onClick={() => setConvertId(null)}
            sx={{
              bgcolor: ds.paper, border: `1px solid ${ds.borderInput}`, color: '#414141',
              '&:hover': { bgcolor: ds.hairline, border: `1px solid ${ds.borderInput}` },
            }}
          >
            {t('inbox.cancel')}
          </Button>
          <Button variant="contained" onClick={() => convert.mutate()} disabled={!convTitle}>{t('inbox.convert')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Inbox;
