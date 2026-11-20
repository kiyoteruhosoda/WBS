import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import App from './App';
import { MaintenanceGate } from './components/MaintenanceScreen';
import { checkService, currentOutage, subscribeOutage } from './pwa/maintenance';
import { theme } from './theme';
import './index.css';

/**
 * The maintenance screen (task #655, ADR-0075).
 *
 * ⚠ **Drawn in a root separate from the app.** The app is only hidden, never unmounted, so when the edge opens again
 * the same screen comes back with anything half-typed still in place. The root is made the first time it closes.
 */
const watchOutage = (): void => {
  const app = document.getElementById('root');
  let mounted = false;
  const sync = () => {
    const closed = currentOutage() !== null;
    if (app) app.hidden = closed;
    if (!closed || mounted) return;
    mounted = true;
    const container = document.createElement('div');
    container.id = 'maintenance-root';
    document.body.append(container);
    ReactDOM.createRoot(container).render(
      <React.StrictMode>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <MaintenanceGate check={() => checkService()} />
        </ThemeProvider>
      </React.StrictMode>,
    );
  };
  subscribeOutage(sync);
  sync();
};

watchOutage();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
