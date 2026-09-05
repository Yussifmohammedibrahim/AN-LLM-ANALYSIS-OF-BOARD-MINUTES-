import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { authAPI } from '../api/api';
import { Mail, ArrowLeft, ShieldCheck, AlertCircle } from 'lucide-react';
import { notifyError, notifySuccess } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';

const ForgotPassword = () => {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const {
    register,
    handleSubmit,
    formState: { errors },
    clearErrors,
    watch
  } = useForm({
    defaultValues: {
      email: ''
    }
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const emailValue = watch('email') || '';

  const onSubmit = async (data) => {
    clearErrors();
    setIsSubmitting(true);
    try {
      await authAPI.forgotPassword(String(data.email || '').trim().toLowerCase());
      notifySuccess(t('authForgotRequestReceived'));
    } catch (error) {
      notifyError(error.response?.data?.error || t('authForgotRequestFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">
            <Mail size={32} />
          </div>
          <h1 className="login-title">{t('authForgotTitle')}</h1>
          <p className="login-subtitle">{t('authForgotSubtitle')}</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="login-form" noValidate>
          <div className="form-group">
            <label className="form-label">{t('authEmailAddress')}</label>
            <input
              type="email"
              className={`form-input ${errors.email ? 'error' : ''}`}
              placeholder={t('authEmailPlaceholder')}
              autoComplete="email"
              disabled={isSubmitting}
              {...register('email', {
                required: t('authEmailRequired'),
                pattern: {
                  value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                  message: t('authEmailInvalid')
                }
              })}
            />
            {errors.email && (
              <p className="form-error">
                <AlertCircle size={14} />
                {errors.email.message}
              </p>
            )}
          </div>

          <div className="auth-actions">
            <button
              type="submit"
              className="auth-btn auth-btn-primary"
              disabled={isSubmitting || !emailValue.trim()}
            >
              <ShieldCheck size={16} />
              {isSubmitting ? t('authSendingResetLink') : t('authSendResetLink')}
            </button>
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="auth-btn auth-btn-secondary"
              disabled={isSubmitting}
            >
              <ArrowLeft size={20} className="mr-2" />
              {t('authBackToLogin')}
            </button>
          </div>
        </form>

        <div className="login-hint">{t('authForgotHint')}</div>

        <div className="login-footer">
          <p className="login-support">
            {t('authForgotSupport')}
          </p>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;

