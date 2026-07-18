import React, { useMemo } from 'react';
import { Box, Checkbox } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import type { Task, Category } from '../types';
import { displayStatus } from '../utils/format';
import type { DisplayStatus } from '../utils/format';
import { ds } from '../theme';
import CategoryDot from './CategoryDot';
import PriorityChip from './PriorityChip';

const DAY_WIDTH = 54;
const ROW_HEIGHT = 40;
const HEADER_HEIGHT = 56;
const LEFT_WIDTH = 360;
const MAX_DAYS = 90;

const dateOnly = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const addDays = (d: Date, n: number): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const diffDays = (a: Date, b: Date): number => Math.round((dateOnly(a).getTime() - dateOnly(b).getTime()) / 86400000);
const parse = (s: string | null): Date | null => {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : dateOnly(d);
};

// ステータス→バー色（トラック / フィル）
const barColors: Record<DisplayStatus, { track: string; fill: string }> = {
  DOING: { track: ds.ganttDoingTrack, fill: ds.primary },
  DONE: { track: ds.successPale2, fill: ds.success },
  TODO: { track: 'transparent', fill: 'transparent' },
  WAITING: { track: ds.warnPale, fill: ds.warnText },
  CANCELLED: { track: ds.track, fill: ds.todoGray },
  LATE: { track: ds.ganttLateTrack, fill: ds.danger },
};

interface Props {
  tasks: Task[];
  categories?: Category[];
  showMeta?: boolean;
  onToggleDone?: (task: Task) => void;
}

const GanttChart: React.FC<Props> = ({ tasks, categories, showMeta = true, onToggleDone }) => {
  const navigate = useNavigate();
  const today = dateOnly(new Date());

  const { rangeStart, days } = useMemo(() => {
    let min = addDays(today, -3);
    let max = addDays(today, 10);
    for (const t of tasks) {
      const s = parse(t.start_date) ?? parse(t.due_date);
      const e = parse(t.due_date) ?? parse(t.start_date);
      if (s && s < min) min = s;
      if (e && e > max) max = e;
    }
    min = addDays(min, -1);
    max = addDays(max, 1);
    let n = diffDays(max, min) + 1;
    if (n > MAX_DAYS) n = MAX_DAYS;
    return { rangeStart: min, days: Array.from({ length: n }, (_, i) => addDays(min, i)) };
  }, [tasks, today]);

  const todayIdx = diffDays(today, rangeStart);
  const timelineWidth = days.length * DAY_WIDTH;

  return (
    <Box sx={{ display: 'flex', border: `1px solid ${ds.border}`, borderRadius: '10px', bgcolor: ds.paper, overflow: 'hidden' }}>
      {/* 左: タスク名パネル */}
      <Box sx={{ width: { xs: 220, md: LEFT_WIDTH }, flexShrink: 0, borderRight: `1px solid ${ds.border}` }}>
        <Box sx={{
          height: HEADER_HEIGHT, display: 'flex', alignItems: 'center', px: '14px',
          bgcolor: '#F7F7F8', borderBottom: `1px solid ${ds.border}`,
          fontSize: 13, fontWeight: 700, color: ds.textSub,
        }}>
          タスク名
        </Box>
        {tasks.map((t) => (
          <Box key={t.id} sx={{
            height: ROW_HEIGHT, display: 'flex', alignItems: 'center', gap: '8px', px: '8px',
            borderBottom: '1px solid #ECECEE', '&:last-child': { borderBottom: 'none' },
          }}>
            <Checkbox
              size="small"
              checked={t.status === 'DONE'}
              onChange={() => onToggleDone?.(t)}
              sx={{ p: '4px', color: ds.todoGray, '&.Mui-checked': { color: ds.success } }}
            />
            <CategoryDot categoryId={t.category_id} categories={categories} size={7} />
            <Box
              onClick={() => navigate(`/tasks/${t.id}`)}
              sx={{
                flex: 1, minWidth: 0, fontSize: 13, color: ds.text, cursor: 'pointer',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                textDecoration: t.status === 'DONE' ? 'line-through' : 'none',
                '&:hover': { color: ds.primary },
              }}
            >
              {t.title}
            </Box>
            {showMeta && <PriorityChip priority={t.priority} />}
          </Box>
        ))}
      </Box>

      {/* 右: タイムライン */}
      <Box sx={{ flex: 1, minWidth: 0, overflowX: 'auto' }}>
        <Box sx={{ position: 'relative', width: timelineWidth }}>
          {/* ヘッダ */}
          <Box sx={{ display: 'flex', height: HEADER_HEIGHT, bgcolor: '#F7F7F8', borderBottom: `1px solid ${ds.border}` }}>
            {days.map((d, i) => {
              const dow = d.getDay();
              const color = dow === 0 ? ds.dangerText : dow === 6 ? ds.primary : ds.textSub;
              return (
                <Box key={i} sx={{
                  width: DAY_WIDTH, flexShrink: 0, textAlign: 'center', pt: '9px',
                  borderLeft: i === 0 ? 'none' : '1px solid #ECECEE',
                  bgcolor: dow === 0 || dow === 6 ? '#F1F1F3' : 'transparent',
                }}>
                  <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text }}>{d.getMonth() + 1}/{d.getDate()}</Box>
                  <Box sx={{ fontSize: 11, color }}>{['日', '月', '火', '水', '木', '金', '土'][dow]}</Box>
                </Box>
              );
            })}
          </Box>

          {/* 行グリッド + バー */}
          <Box sx={{ position: 'relative' }}>
            {/* 縦グリッド・土日シェード */}
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', pointerEvents: 'none' }}>
              {days.map((d, i) => {
                const dow = d.getDay();
                return (
                  <Box key={i} sx={{
                    width: DAY_WIDTH, flexShrink: 0,
                    borderLeft: i === 0 ? 'none' : '1px solid #F2F2F3',
                    bgcolor: dow === 0 || dow === 6 ? '#FAFAFB' : 'transparent',
                  }} />
                );
              })}
            </Box>

            {tasks.map((t) => {
              const st = displayStatus(t);
              const s = parse(t.start_date) ?? parse(t.due_date);
              const e = parse(t.due_date) ?? parse(t.start_date);
              let bar: React.ReactNode = null;
              if (s && e) {
                const startIdx = Math.max(0, diffDays(s, rangeStart));
                const endIdx = Math.min(days.length - 1, diffDays(e, rangeStart));
                if (endIdx >= 0 && startIdx <= days.length - 1 && endIdx >= startIdx) {
                  const left = startIdx * DAY_WIDTH + 3;
                  const width = (endIdx - startIdx + 1) * DAY_WIDTH - 6;
                  const colors = barColors[st];
                  const fillPct = st === 'DONE' ? 100 : Math.max(0, Math.min(100, t.progress_percent));
                  bar = (
                    <Box
                      onClick={() => navigate(`/tasks/${t.id}`)}
                      sx={{
                        position: 'absolute', left, width, top: (ROW_HEIGHT - 22) / 2, height: 22,
                        borderRadius: '6px', cursor: 'pointer', overflow: 'hidden',
                        bgcolor: colors.track,
                        border: st === 'TODO' ? `1.5px dashed ${ds.todoGray}` : 'none',
                      }}
                      title={`${t.title}（${t.progress_percent}%）`}
                    >
                      {st !== 'TODO' && (
                        <Box sx={{ width: `${fillPct}%`, height: '100%', borderRadius: '6px', bgcolor: colors.fill }} />
                      )}
                    </Box>
                  );
                }
              }
              return (
                <Box key={t.id} sx={{
                  position: 'relative', height: ROW_HEIGHT,
                  borderBottom: '1px solid #ECECEE', '&:last-child': { borderBottom: 'none' },
                }}>
                  {bar}
                </Box>
              );
            })}

            {/* 今日ライン */}
            {todayIdx >= 0 && todayIdx < days.length && (
              <Box sx={{
                position: 'absolute', top: 0, bottom: 0, pointerEvents: 'none',
                left: todayIdx * DAY_WIDTH + DAY_WIDTH / 2, width: 0, borderLeft: `2px solid ${ds.danger}`,
              }} />
            )}
          </Box>

          {/* 今日ラベル（ヘッダ上） */}
          {todayIdx >= 0 && todayIdx < days.length && (
            <Box sx={{
              position: 'absolute', top: HEADER_HEIGHT - 16,
              left: todayIdx * DAY_WIDTH + DAY_WIDTH / 2, transform: 'translateX(-50%)',
              bgcolor: ds.danger, color: '#fff', fontSize: 10, fontWeight: 700,
              px: '6px', py: '1px', borderRadius: '4px', pointerEvents: 'none',
            }}>
              今日
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default GanttChart;
