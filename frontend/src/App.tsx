import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { theme } from './theme';
import Layout from './components/Layout';
import Today from './pages/Today';
import TaskList from './pages/TaskList';
import TaskEdit from './pages/TaskEdit';
import GanttPage from './pages/GanttPage';
import ActualsPage from './pages/ActualsPage';
import CalendarPage from './pages/CalendarPage';
import ClosingPage from './pages/ClosingPage';
import Inbox from './pages/Inbox';
import CategoriesPage from './pages/CategoriesPage';
import MilestonesPage from './pages/MilestonesPage';
import ProjectsPage from './pages/ProjectsPage';
import Settings from './pages/Settings';
import AppReturnPage from './pages/AppReturnPage';
import { I18nProvider } from './i18n';
import { AuthProvider } from './auth/AuthProvider';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } });

/** ログインの内側の画面（SSO 有効なら未ログインでログイン画面を出す）。 */
const SignedInApp: React.FC = () => (
  <AuthProvider>
    <I18nProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* 「今日」が最初の画面（ダッシュボードはここへ寄せた。ADR-0015）。古い /today は寄せ先へ */}
          <Route index element={<Today />} />
          <Route path="today" element={<Navigate to="/" replace />} />
          <Route path="tasks" element={<TaskList />} />
          <Route path="tasks/new" element={<TaskEdit />} />
          <Route path="tasks/:id" element={<TaskEdit />} />
          <Route path="gantt" element={<GanttPage />} />
          {/* 実績の見える化。/actuals/review は締めの直後に「残を見直す」（task #162） */}
          <Route path="actuals" element={<ActualsPage />} />
          <Route path="actuals/:view" element={<ActualsPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="closing" element={<ClosingPage />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="milestones" element={<MilestonesPage />} />
          <Route path="settings" element={<Settings />} />
          {/* ログイン済みで /login に来た場合（コールバック後の戻り先など）は最初の画面へ */}
          <Route path="login" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </I18nProvider>
  </AuthProvider>
);

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          {/* 打刻アプリのログインの戻り先（ADR-0019）。ログインの外に置く（未ログインの PC で開いてもログイン画面へ飛ばさない） */}
          <Route path="/app/oauth2redirect" element={<AppReturnPage />} />
          <Route path="*" element={<SignedInApp />} />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
