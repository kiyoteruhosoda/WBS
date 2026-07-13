import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { AppBar, Box, Card, CardContent, Container, Grid, List, ListItem, Toolbar, Typography } from '@mui/material';

const api = (path: string) => fetch(`/api${path}`).then((r) => r.json());
const queryClient = new QueryClient();

function Dashboard() {
  const { data } = useQuery({ queryKey: ['dashboard'], queryFn: () => api('/dashboard') });
  return <Grid container spacing={2}>{Object.entries(data?.kpi ?? {}).map(([k, v]) => <Grid item xs={12} md={3} key={k}><Card><CardContent><Typography variant="overline">{k}</Typography><Typography variant="h4">{String(v)}</Typography></CardContent></Card></Grid>)}</Grid>;
}
function Today() {
  const { data = [] } = useQuery({ queryKey: ['today'], queryFn: () => api('/today-tasks') });
  return <List>{data.map((t: any) => <ListItem key={t.id}>{t.bucket}: {t.title} ({t.progress_percent}%)</ListItem>)}</List>;
}
function Tasks() {
  const { data = [] } = useQuery({ queryKey: ['tasks'], queryFn: () => api('/tasks') });
  return <List>{data.map((t: any) => <ListItem key={t.id}>{t.title} / {t.status} / score {t.score}</ListItem>)}</List>;
}
function Simple({ name }: { name: string }) { return <Typography variant="h5">{name}</Typography>; }
function App() { return <QueryClientProvider client={queryClient}><BrowserRouter><AppBar position="static"><Toolbar><Typography variant="h6">Task Scheduler</Typography><Box sx={{ml:2, display:'flex', gap:2}}>{['/','/today','/tasks','/gantt','/calendar','/inbox','/milestones','/weekly-review'].map(p=><Link style={{color:'white'}} to={p} key={p}>{p}</Link>)}</Box></Toolbar></AppBar><Container sx={{mt:3}}><Routes><Route path="/" element={<Dashboard/>}/><Route path="/today" element={<Today/>}/><Route path="/tasks" element={<Tasks/>}/><Route path="/gantt" element={<Simple name="ガントチャート"/>}/><Route path="/calendar" element={<Simple name="カレンダー"/>}/><Route path="/inbox" element={<Simple name="Inbox"/>}/><Route path="/milestones" element={<Simple name="マイルストーン"/>}/><Route path="/weekly-review" element={<Simple name="週次レビュー"/>}/></Routes></Container></BrowserRouter></QueryClientProvider>; }

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
