import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, CircularProgress, Alert, TextField, Button, List,
  ListItem, ListItemText, IconButton, Divider, Dialog, DialogTitle,
  DialogContent, DialogActions, FormControl, InputLabel, Select, MenuItem,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import AddIcon from '@mui/icons-material/Add';
import { getInbox, createInboxItem, convertInboxItem, deleteInboxItem } from '../api/inbox';
import { getCategories } from '../api/categories';
import type { TaskStatus } from '../types';
import { formatDate } from '../utils/format';

const Inbox: React.FC = () => {
  const qc = useQueryClient();
  const [title, setTitle] = useState('');
  const [memo, setMemo] = useState('');
  const [convertId, setConvertId] = useState<number | null>(null);
  const [convTitle, setConvTitle] = useState('');
  const [convStatus, setConvStatus] = useState<TaskStatus>('TODO');
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
      title: convTitle, status: convStatus,
      due_date: convDue || null, category_id: convCat ? Number(convCat) : null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inbox'] }); setConvertId(null); },
  });

  const openConvert = (id: number, itemTitle: string) => {
    setConvertId(id); setConvTitle(itemTitle); setConvStatus('TODO'); setConvDue(''); setConvCat('');
  };

  if (isLoading) return <CircularProgress />;
  if (error) return <Alert severity="error">読み込みエラー</Alert>;

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>インボックス</Typography>
      <Box sx={{ display: 'flex', gap: 1, mb: 3, flexWrap: 'wrap' }}>
        <TextField size="small" label="タイトル" value={title} onChange={e => setTitle(e.target.value)} sx={{ flex: 1, minWidth: 200 }} />
        <TextField size="small" label="メモ (任意)" value={memo} onChange={e => setMemo(e.target.value)} sx={{ flex: 1, minWidth: 200 }} />
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => add.mutate()} disabled={!title}>追加</Button>
      </Box>
      <List>
        {data?.map(item => (
          <React.Fragment key={item.id}>
            <ListItem secondaryAction={
              <Box sx={{ display: 'flex', gap: 1 }}>
                {!item.converted_task_id && (
                  <IconButton edge="end" title="タスクに変換" onClick={() => openConvert(item.id, item.title)}>
                    <SwapHorizIcon />
                  </IconButton>
                )}
                <IconButton edge="end" onClick={() => del.mutate(item.id)}><DeleteIcon /></IconButton>
              </Box>
            }>
              <ListItemText
                primary={item.title}
                secondary={`${formatDate(item.created_at)}${item.converted_task_id ? ' ✅ 変換済み' : ''}`}
              />
            </ListItem>
            <Divider />
          </React.Fragment>
        ))}
        {data?.length === 0 && <Typography variant="body2" color="text.secondary">インボックスは空です</Typography>}
      </List>

      <Dialog open={convertId !== null} onClose={() => setConvertId(null)} maxWidth="sm" fullWidth>
        <DialogTitle>タスクに変換</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField label="タイトル" value={convTitle} onChange={e => setConvTitle(e.target.value)} fullWidth />
            <FormControl fullWidth>
              <InputLabel>ステータス</InputLabel>
              <Select value={convStatus} label="ステータス" onChange={e => setConvStatus(e.target.value as TaskStatus)}>
                {(['TODO','DOING','WAITING'] as TaskStatus[]).map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField type="date" label="期日" slotProps={{ inputLabel: { shrink: true } }} value={convDue} onChange={e => setConvDue(e.target.value)} fullWidth />
            <FormControl fullWidth>
              <InputLabel>カテゴリ</InputLabel>
              <Select value={convCat} label="カテゴリ" onChange={e => setConvCat(e.target.value)}>
                <MenuItem value="">なし</MenuItem>
                {categories?.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConvertId(null)}>キャンセル</Button>
          <Button variant="contained" onClick={() => convert.mutate()} disabled={!convTitle}>変換</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Inbox;
