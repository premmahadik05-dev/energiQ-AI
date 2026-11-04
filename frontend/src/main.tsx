import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from './App';
import { applyTheme, readThemeChoice } from './hooks/useTheme';
import { AppProviders } from './providers';
import './index.css';

applyTheme(readThemeChoice());

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppProviders>
        <AppRoutes />
      </AppProviders>
    </BrowserRouter>
  </StrictMode>,
);
