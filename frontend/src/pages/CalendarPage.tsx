import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, CircularProgress, Alert, IconButton } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { getTasks } from '../api/tasks';
import { getMilestones } from '../api/milestones';
import { getCategories } from '../api/categories';
import { ds, categoryColor } from '../theme';
import { parseDate } from '../utils/format';
import { ChevronLeftIcon, ChevronRightIcon } from '../components/icons';

interface Pill {
  key: string;
  label: string;
  color: string;
  taskId?: number;
}

const dateKey = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const CalendarPage: React.FC = () => {
  const navigate = useNavigate();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth()); // 0-11

  const { data: tasksData, isLoading, error } = useQuery({ queryKey: ['tasks'], queryFn: () => getTasks() });
  const { data: milestones } = useQuery({ queryKey: ['milestones'], queryFn: getMilestones });
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: getCategories });

  const pillMap = useMemo(() => {
    const map = new Map<string, Pill[]>();
    const push = (key: string, pill: Pill) => {
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(pill);
    };
    for (const t of tasksData ?? []) {
      const d = parseDate(t.due_date);
      if (!d) continue;
      const cat = categories?.find((c) => c.id === t.category_id);
      push(dateKey(d), { key: `task-${t.id}`, label: t.title, color: categoryColor(t.category_id, cat?.color), taskId: t.id });
    }
    for (const m of milestones ?? []) {
      const d = parseDate(m.due_date);
      if (!d) continue;
      push(dateKey(d), { key: `ms-${m.id}`, label: `◆ ${m.name}`, color: '#6B46C1' });
    }
    return map;
  }, [tasksData, milestones, categories]);

  // 月グリッド（日曜はじまり・当月を含む週すべて）
  const cells = useMemo(() => {
    const first = new Date(year, month, 1);
    const start = new Date(year, month, 1 - first.getDay());
    const lastDay = new Date(year, month + 1, 0);
    const weeks = Math.ceil((first.getDay() + lastDay.getDate()) / 7);
    return Array.from({ length: weeks * 7 }, (_, i) =>
      new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  }, [year, month]);

  const moveMonth = (delta: number) => {
    const d = new Date(year, month + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth());
  };

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">データの読み込みに失敗しました</Alert>;

  const todayKey = dateKey(new Date());

  return (
    <Box>
      {/* カレンダーコントロール */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '10px', mb: '14px' }}>
        <IconButton
          onClick={() => moveMonth(-1)}
          sx={{ border: `1px solid ${ds.border}`, borderRadius: '8px', width: 34, height: 34, color: ds.textSub }}
        >
          <ChevronLeftIcon size={16} />
        </IconButton>
        <Box sx={{ fontSize: 18, fontWeight: 700, color: ds.text, minWidth: 130, textAlign: 'center' }}>
          {year}年{month + 1}月
        </Box>
        <IconButton
          onClick={() => moveMonth(1)}
          sx={{ border: `1px solid ${ds.border}`, borderRadius: '8px', width: 34, height: 34, color: ds.textSub }}
        >
          <ChevronRightIcon size={16} />
        </IconButton>
        <Button
          variant="text"
          onClick={() => { setYear(now.getFullYear()); setMonth(now.getMonth()); }}
          sx={{ color: ds.primary, fontWeight: 700, px: '10px', py: '4px' }}
        >
          今日
        </Button>
      </Box>

      <Box sx={{ bgcolor: ds.paper, border: `1px solid ${ds.border}`, borderRadius: '10px', overflow: 'hidden' }}>
        {/* 曜日ヘッダ */}
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', bgcolor: '#F7F7F8', borderBottom: `1px solid ${ds.border}` }}>
          {['日', '月', '火', '水', '木', '金', '土'].map((w, i) => (
            <Box key={w} sx={{
              textAlign: 'center', py: '10px', fontSize: 13, fontWeight: 700,
              color: i === 0 ? ds.dangerText : i === 6 ? ds.primary : ds.textSub,
            }}>
              {w}
            </Box>
          ))}
        </Box>

        {/* 日付グリッド */}
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>
          {cells.map((d, i) => {
            const inMonth = d.getMonth() === month;
            const key = dateKey(d);
            const isToday = key === todayKey;
            const dow = d.getDay();
            const pills = pillMap.get(key) ?? [];
            const numColor = !inMonth ? '#B7B7BB' : dow === 0 ? ds.dangerText : dow === 6 ? ds.primary : ds.text;
            return (
              <Box key={i} sx={{
                minHeight: { xs: 72, md: 104 }, p: '6px',
                borderBottom: '1px solid #ECECEE',
                borderLeft: i % 7 === 0 ? 'none' : '1px solid #ECECEE',
                bgcolor: inMonth ? 'transparent' : '#FAFAFB',
              }}>
                <Box sx={{ display: 'flex', mb: '4px' }}>
                  {isToday ? (
                    <Box sx={{
                      width: 24, height: 24, borderRadius: '50%', bgcolor: ds.primary, color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700,
                    }}>
                      {d.getDate()}
                    </Box>
                  ) : (
                    <Box sx={{ fontSize: 13, fontWeight: 700, color: numColor, px: '4px' }}>{d.getDate()}</Box>
                  )}
                </Box>
                {pills.slice(0, 2).map((p) => (
                  <Box
                    key={p.key}
                    onClick={p.taskId != null ? () => navigate(`/tasks/${p.taskId}`) : undefined}
                    sx={{
                      bgcolor: p.color, color: '#fff', fontSize: 11, fontWeight: 700,
                      borderRadius: '4px', px: '6px', py: '1px', mb: '3px',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      cursor: p.taskId != null ? 'pointer' : 'default',
                      '&:hover': p.taskId != null ? { opacity: 0.85 } : undefined,
                    }}
                    title={p.label}
                  >
                    {p.label}
                  </Box>
                ))}
                {pills.length > 2 && (
                  <Box sx={{ fontSize: 11, color: ds.textMuted, px: '4px' }}>+{pills.length - 2}</Box>
                )}
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
};

export default CalendarPage;
