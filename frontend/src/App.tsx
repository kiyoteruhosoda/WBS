import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { theme } from './theme';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Today from './pages/Today';
import TaskList from './pages/TaskList';
import TaskEdit from './pages/TaskEdit';
import GanttPage from './pages/GanttPage';
import CalendarPage from './pages/CalendarPage';
import Inbox from './pages/Inbox';
import Settings from './pages/Settings';
import { I18nProvider } from './i18n';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <I18nProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="today" element={<Today />} />
            <Route path="tasks" element={<TaskList />} />
            <Route path="tasks/new" element={<TaskEdit />} />
            <Route path="tasks/:id" element={<TaskEdit />} />
            <Route path="gantt" element={<GanttPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="inbox" element={<Inbox />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </I18nProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
