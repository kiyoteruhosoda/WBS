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

// Show/hide "offline" based on fetch results (task #192 / ADR-0028). Offline when a fetch fails with no response, back once anything succeeds
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

/** Screens behind sign-in (with SSO enabled, signed-out users get the sign-in page). */
const SignedInApp: React.FC = () => (
  <AuthProvider>
    <I18nProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* The first screen is tasks ("today" was removed. task #543, ADR-0070) */}
          <Route index element={<Navigate to="/tasks" replace />} />
          <Route path="tasks" element={<TaskList />} />
          <Route path="tasks/new" element={<TaskEdit />} />
          <Route path="tasks/:id" element={<TaskEdit />} />
          <Route path="gantt" element={<GanttPage />} />
          {/* Actuals visualization. /actuals/review is "review remaining" after Tracker's closing arrives (task #162) */}
          <Route path="actuals" element={<ActualsPage />} />
          <Route path="actuals/:view" element={<ActualsPage />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="milestones" element={<MilestonesPage />} />
          <Route path="settings" element={<Settings />} />
          {/* Signed-in visits to /login (e.g. return after callback) go to the first screen */}
          <Route path="login" element={<Navigate to="/" replace />} />
          {/* Old bookmarks of removed screens (today, calendar, closing, rules, etc.) go to the first screen */}
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
      {/* The new-version notice is shown as the topmost bar on every screen (ADR-0072), including the sign-in page.
          Placed before the screens so the bar sits above the header */}
      <AppUpdatePrompt watch={watchForUpdate} />
      <BrowserRouter>
        <SignedInApp />
      </BrowserRouter>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
