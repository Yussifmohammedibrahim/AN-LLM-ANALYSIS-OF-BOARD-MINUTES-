import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CircleHelp, PencilLine } from 'lucide-react';
import './ConfirmModal.css';

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [opts, setOpts] = useState({ open: false });
  const [resolver, setResolver] = useState(null);
  const [promptValue, setPromptValue] = useState('');
  const [promptError, setPromptError] = useState('');
  const promptTrim = opts.trim;
  const promptValidate = opts.validate;

  const confirm = useCallback((options = {}) => {
    return new Promise((resolve) => {
      setPromptValue('');
      setPromptError('');
      const incomingActions = Array.isArray(options.actions) ? options.actions : [];
      const actions = incomingActions.length > 0
        ? incomingActions
        : [{ label: 'OK', value: 'ok', variant: 'primary' }];
      const tone = options.tone
        || (actions.some((action) => action?.variant === 'danger') ? 'danger' : 'default');

      setOpts({
        open: true,
        mode: 'confirm',
        title: options.title || 'Confirm',
        message: options.message || '',
        actions,
        showCancel: options.showCancel !== false,
        cancelLabel: options.cancelLabel || 'Cancel',
        tone,
        dismissOnBackdrop: options.dismissOnBackdrop !== false,
      });
      setResolver(() => resolve);
    });
  }, []);

  const prompt = useCallback((options = {}) => {
    return new Promise((resolve) => {
      setPromptValue(String(options.defaultValue || ''));
      setPromptError('');
      setOpts({
        open: true,
        mode: 'prompt',
        title: options.title || 'Input Required',
        message: options.message || '',
        inputLabel: options.inputLabel || '',
        placeholder: options.placeholder || '',
        validate: options.validate || null,
        trim: options.trim !== false,
        submitLabel: options.submitLabel || 'Continue',
        showCancel: options.showCancel !== false,
        cancelLabel: options.cancelLabel || 'Cancel',
        tone: options.tone || 'default',
        dismissOnBackdrop: options.dismissOnBackdrop !== false,
      });
      setResolver(() => resolve);
    });
  }, []);

  const close = useCallback((result) => {
    setOpts((s) => ({ ...s, open: false }));
    setPromptError('');
    if (resolver) {
      resolver(result);
      setResolver(null);
    }
  }, [resolver]);

  const submitPrompt = useCallback(() => {
    const raw = String(promptValue || '');
    const value = promptTrim === false ? raw : raw.trim();

    if (typeof promptValidate === 'function') {
      const verdict = promptValidate(value);
      if (verdict !== true) {
        setPromptError(typeof verdict === 'string' ? verdict : 'Invalid input.');
        return;
      }
    }

    close({ action: 'submit', value });
  }, [close, promptTrim, promptValidate, promptValue]);

  useEffect(() => {
    if (!opts.open) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        close({ action: 'cancel', value: null });
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [close, opts.open]);

  const DialogIcon = useMemo(() => {
    if (opts.mode === 'prompt') return PencilLine;
    if (opts.tone === 'danger') return AlertTriangle;
    return CircleHelp;
  }, [opts.mode, opts.tone]);

  return (
    <ConfirmContext.Provider value={{ confirm, prompt }}>
      {children}
      {opts.open && (
        <div
          className="confirm-overlay"
          onMouseDown={() => {
            if (opts.dismissOnBackdrop) close({ action: 'cancel', value: null });
          }}
        >
          <div
            className="confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-message"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="confirm-header">
              <div className={`confirm-icon confirm-icon-${opts.tone || 'default'}`}>
                <DialogIcon size={18} />
              </div>
              <div className="confirm-header-text">
                {opts.title && <h3 id="confirm-title" className="confirm-title">{opts.title}</h3>}
                <div id="confirm-message" className="confirm-body">{opts.message}</div>
              </div>
            </div>
            {opts.mode === 'prompt' && (
              <div className="confirm-prompt-wrap">
                {opts.inputLabel ? <label className="confirm-prompt-label">{opts.inputLabel}</label> : null}
                <input
                  type="text"
                  className="confirm-prompt-input"
                  value={promptValue}
                  placeholder={opts.placeholder}
                  onChange={(e) => {
                    setPromptValue(e.target.value);
                    if (promptError) setPromptError('');
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      submitPrompt();
                    }
                  }}
                  autoFocus
                />
                {promptError ? <div className="confirm-prompt-error">{promptError}</div> : null}
              </div>
            )}
            <div className="confirm-actions">
              {opts.showCancel && (
                <button
                  type="button"
                  className="confirm-action-btn confirm-action-secondary"
                  onClick={() => close({ action: 'cancel', value: null })}
                >
                  {opts.cancelLabel}
                </button>
              )}
              {opts.mode === 'prompt' ? (
                <button type="button" className="confirm-action-btn confirm-action-primary" onClick={submitPrompt}>
                  {opts.submitLabel}
                </button>
              ) : (
                (opts.actions || []).map((a, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`confirm-action-btn ${a.variant === 'danger' ? 'confirm-action-danger' : a.variant === 'primary' ? 'confirm-action-primary' : 'confirm-action-secondary'}`}
                    onClick={() => close({ action: a.value ?? a.label })}
                    autoFocus={Boolean(a.autoFocus)}
                  >
                    {a.label}
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm must be used within a ConfirmProvider');
  return ctx.confirm;
}

export function usePrompt() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('usePrompt must be used within a ConfirmProvider');
  return ctx.prompt;
}

export default ConfirmProvider;
