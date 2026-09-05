import React, { useEffect } from 'react';
import './ConfirmModal.css';

const ConfirmModal = ({ open, title, message, children, onCancel, actions = [] }) => {
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape' && open) onCancel && onCancel();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="confirm-modal-overlay" role="presentation" onMouseDown={onCancel}>
      <div
        className="confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="confirm-modal-header">
          <h3 id="confirm-modal-title">{title}</h3>
        </div>
        <div className="confirm-modal-body">
          {message && <p className="confirm-modal-message">{message}</p>}
          {children}
        </div>
        <div className="confirm-modal-footer">
          <button className="confirm-btn cancel" onClick={onCancel}>Cancel</button>
          {actions.map((a, i) => (
            <button
              key={i}
              className={`confirm-btn ${a.variant || 'primary'}`}
              onClick={() => a.onClick && a.onClick()}
              autoFocus={a.autoFocus}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;
