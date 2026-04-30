import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary
      fallbackTitle="Workstation display unavailable"
      fallbackMessage="The app shell caught a rendering problem. Use Retry after the latest data refresh completes."
    >
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);

