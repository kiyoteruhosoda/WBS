import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { theme } from './theme';
import Layout from './components/Layout';
import TaskList from './pages/TaskList';
import TaskEdit from './pages/TaskEdit';
import GanttPage from './pages/GanttPage';
import ActualsPage from './pages/ActualsPage';
import Inbox from './pages/Inbox';
import CategoriesPage from './pages/CategoriesPage';
import MilestonesPage from './pages/MilestonesPage';
import ProjectsPage from './pages/ProjectsPage';
import Settings from './pages/Settings';
import { I18nProvider } from './i18n';
import { AuthProvider } from './auth/AuthProvider';
import AppUpdatePrompt from './components/AppUpdatePrompt';
import { watchForUpdate } from './pwa/appUpdate';
import { isNetworkFailure, noteRequestOutcome } from './pwa/connectivity';

// 取得の成否で「オフラインです」を出し消しする（task #192 / ADR-0028）。応答なしで落ちたらオフライン、何か取れたら戻す
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
  queryCache: new QueryCache({
    onError: (error) => noteRequestOutcome(isNetworkFailure(error)),
    onSuccess: () => noteRequestOutcome(false),
  }),
  mutationCache: new MutationCache({
    onError: (error) => noteRequestOutcome(isNetworkFailure(error)),
    onSuccess: () => noteRequestOutcome(false),
  }),
});

/** ログインの内側の画面（SSO 有効なら未ログインでログイン画面を出す）。 */
const SignedInApp: React.FC = () => (
  <AuthProvider>
    <I18nProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* 最初の画面はタスク（「今日」は外した。task #543・ADR-0070） */}
          <Route index element={<Navigate to="/tasks" replace />} />
          <Route path="tasks" element={<TaskList />} />
          <Route path="tasks/new" element={<TaskEdit />} />
          <Route path="tasks/:id" element={<TaskEdit />} />
          <Route path="gantt" element={<GanttPage />} />
          {/* 実績の見える化。/actuals/review は Tracker の締めが届いた後に「残を見直す」（task #162） */}
          <Route path="actuals" element={<ActualsPage />} />
          <Route path="actuals/:view" element={<ActualsPage />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="milestones" element={<MilestonesPage />} />
          <Route path="settings" element={<Settings />} />
          {/* ログイン済みで /login に来た場合（コールバック後の戻り先など）は最初の画面へ */}
          <Route path="login" element={<Navigate to="/" replace />} />
          {/* 外した画面（今日・カレンダー・締め・規則など）の古いブックマークは最初の画面へ */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </I18nProvider>
  </AuthProvider>
);

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {/* 新しい版の知らせはどの画面でもいちばん上の帯に出す（ADR-0072）。ログイン画面でも出す。
          帯がヘッダーの上に来るよう、画面より前に置く */}
      <AppUpdatePrompt watch={watchForUpdate} />
      <BrowserRouter>
        <SignedInApp />
      </BrowserRouter>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
