import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import {
  AppBar,
  Box,
  Card,
  CardContent,
  Container,
  List,
  ListItem,
  Toolbar,
  Typography,
} from '@mui/material';

const api = async <T,>(path: string): Promise<T> => {
  const response = await fetch(`/api${path}`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
};

const queryClient = new QueryClient();

type DashboardResponse = {
  kpi: Record<string, number>;
};

type TaskSummary = {
  id: number;
  title: string;
  status: string;
  bucket?: string;
  progress_percent: number;
  score: number;
};

function Dashboard() {
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api<DashboardResponse>('/dashboard'),
  });

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, 1fr)' }, gap: 2 }}>
      {Object.entries(data?.kpi ?? {}).map(([key, value]) => (
        <Card key={key}>
          <CardContent>
            <Typography variant="overline">{key}</Typography>
            <Typography variant="h4">{value}</Typography>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}

function Today() {
  const { data = [] } = useQuery({
    queryKey: ['today'],
    queryFn: () => api<TaskSummary[]>('/today-tasks'),
  });

  return (
    <List>
      {data.map((task) => (
        <ListItem key={task.id}>
          {task.bucket}: {task.title} ({task.progress_percent}%)
        </ListItem>
      ))}
    </List>
  );
}

function Tasks() {
  const { data = [] } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => api<TaskSummary[]>('/tasks'),
  });

  return (
    <List>
      {data.map((task) => (
        <ListItem key={task.id}>
          {task.title} / {task.status} / score {task.score}
        </ListItem>
      ))}
    </List>
  );
}

function Simple({ name }: { name: string }) {
  return <Typography variant="h5">{name}</Typography>;
}

function App() {
  const paths = ['/', '/today', '/tasks', '/gantt', '/calendar', '/inbox', '/milestones', '/weekly-review'];

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6">Task Scheduler</Typography>
            <Box sx={{ ml: 2, display: 'flex', gap: 2 }}>
              {paths.map((path) => (
                <Link style={{ color: 'white' }} to={path} key={path}>
                  {path}
                </Link>
              ))}
            </Box>
          </Toolbar>
        </AppBar>
        <Container sx={{ mt: 3 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/today" element={<Today />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/gantt" element={<Simple name="ガントチャート" />} />
            <Route path="/calendar" element={<Simple name="カレンダー" />} />
            <Route path="/inbox" element={<Simple name="Inbox" />} />
            <Route path="/milestones" element={<Simple name="マイルストーン" />} />
            <Route path="/weekly-review" element={<Simple name="週次レビュー" />} />
          </Routes>
        </Container>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
