import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './index.css';
import App from './App';
import { ConfirmProvider } from './components/ConfirmProvider';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60000,  // 60s (increased from 30s) - keep data fresh but reduce refetch calls
      gcTime: 10 * 60 * 1000,  // 10 minutes (increased from 5 min) - cache longer for better performance
      retry: 2,  // Increased retries for better resilience
      refetchOnWindowFocus: false,  // Disabled to reduce unnecessary refetches
      refetchOnReconnect: 'stale',  // Only refetch if data is stale when reconnecting
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfirmProvider>
        <App />
      </ConfirmProvider>
    </QueryClientProvider>
  </React.StrictMode>
);