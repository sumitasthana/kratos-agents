import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

const root = document.getElementById('root');
if (!root) throw new Error('Root element not found');

createRoot(root).render(
  // StrictMode temporarily disabled to debug WebSocket disconnections.
  // <StrictMode>
    <App />
  // </StrictMode>
);
