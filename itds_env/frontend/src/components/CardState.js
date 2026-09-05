import React from 'react';
import { Loader2, AlertTriangle, RefreshCw } from 'lucide-react';

const CardState = ({
  status,
  error,
  emptyMessage,
  onRetry,
  isRefreshing,
  children,
}) => {
  if (status === 'loading') {
    return (
      <div className="card-state card-state-loading">
        <Loader2 size={18} className="animate-spin" />
        <span>Loading data...</span>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="card-state card-state-error">
        <AlertTriangle size={16} />
        <span>{error || 'Unable to load this section.'}</span>
        {typeof onRetry === 'function' && (
          <button className="btn btn-outline btn-sm" onClick={onRetry}>
            <RefreshCw size={14} /> Retry
          </button>
        )}
      </div>
    );
  }

  if (status === 'empty') {
    return (
      <div className="card-state card-state-empty">
        <span>{emptyMessage || 'No data available yet.'}</span>
      </div>
    );
  }

  return (
    <div className="card-state-content">
      {isRefreshing && (
        <div className="card-refresh-indicator">
          <Loader2 size={12} className="animate-spin" />
          <span>Refreshing...</span>
        </div>
      )}
      {children}
    </div>
  );
};

export default CardState;
