import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

const bootstrap = window.__JSEARCH_BOOTSTRAP__ || {
  jobs: [],
  appliedCount: 0,
  dismissedCount: 0,
};

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App bootstrap={bootstrap} />
  </React.StrictMode>,
);
