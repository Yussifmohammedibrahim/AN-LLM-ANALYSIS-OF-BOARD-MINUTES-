import React, { useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from "react-hook-form";
import { Eye, EyeOff, AlertCircle, Lock, CheckCircle, XCircle, ArrowLeft, ShieldCheck } from "lucide-react";
import { authAPI } from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';

const getPasswordStrengthState = (password, t) => {
  if (!password) {
    return { level: '', label: '', hint: '' };
  }

  const checks = [
    { ok: password.length >= 8, message: t('authRuleMinLength') },
    { ok: /[A-Z]/.test(password), message: t('authRuleUppercase') },
    { ok: /[a-z]/.test(password), message: t('authRuleLowercase') },
    { ok: /\d/.test(password), message: t('authRuleNumber') },
    { ok: /[!@#$%^&*(),.?":{}|<>]/.test(password), message: t('authRuleSpecial') }
  ];

  const score = checks.reduce((acc, item) => acc + (item.ok ? 1 : 0), 0);
  const firstMissing = checks.find((item) => !item.ok);

  if (score === checks.length) {
    return { level: 'strong', label: t('authPasswordStrengthStrong'), hint: '' };
  }
  if (score >= 3) {
    return {
      level: 'medium',
      label: t('authPasswordStrengthMedium'),
      hint: firstMissing ? firstMissing.message : ''
    };
  }
  return {
    level: 'weak',
    label: t('authPasswordStrengthWeak'),
    hint: firstMissing ? firstMissing.message : ''
  };
};

const ResetPassword = () => {
  const { token } = useParams();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [showPasswords, setShowPasswords] = useState({
    new: false,
    confirm: false
  });

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
    clearErrors
  } = useForm({
    defaultValues: {
      newPassword: '',
      confirmPassword: ''
    }
  });

  const newPassword = watch("newPassword") || '';

  // Password rule checks
  const hasLength = newPassword.length >= 8;
  const hasLower = /[a-z]/.test(newPassword);
  const hasUpper = /[A-Z]/.test(newPassword);
  const hasNumber = /\d/.test(newPassword);
  const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(newPassword);
  const allRulesMet = hasLength && hasLower && hasUpper && hasNumber && hasSpecial;
  const passwordStrength = getPasswordStrengthState(newPassword, t);

  const togglePassword = useCallback((field) => {
    setShowPasswords(prev => ({
      ...prev,
      [field]: !prev[field]
    }));
  }, []);

  const onSubmit = async (data) => {
    clearErrors();
    setLoading(true);
    try {
      await authAPI.resetPassword(token, data.newPassword);
      notifySuccess(t('authResetSuccess'));
      setTimeout(() => navigate('/login'), 2000);
    } catch (error) {
      notifyError(error.response?.data?.error || t('authResetFailed'));
    } finally {
      setLoading(false);
    }
  };

  const [loading, setLoading] = useState(false);

  if (!token) {
    return (
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div className="login-logo">
              <Lock size={32} />
            </div>
            <h1 className="login-title">{t('authInvalidResetTitle')}</h1>
            <p className="login-subtitle">{t('authInvalidResetSubtitle')}</p>
          </div>
          <div className="auth-actions">
            <button type="button" className="auth-btn auth-btn-secondary" onClick={() => navigate('/forgot-password')}>
              {t('authRequestNewLink')}
            </button>
            <button type="button" className="auth-btn auth-btn-primary" onClick={() => navigate('/login')}>
              {t('authBackToLogin')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">
            <Lock size={32} />
          </div>
          <h1 className="login-title">{t('authResetTitle')}</h1>
          <p className="login-subtitle">{t('authResetSubtitle')}</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="login-form" noValidate>
          <div className="form-group">
            <label className="form-label">{t('authNewPassword')} <span className="text-danger">*</span></label>
            <div className="login-input-wrap">
              <input
                type={showPasswords.new ? 'text' : 'password'}
                className={`form-input ${errors.newPassword ? 'error' : ''}`}
                placeholder={t('authNewPasswordPlaceholder')}
                autoComplete="new-password"
                disabled={loading}
                {...register('newPassword', {
                  required: t('authNewPasswordRequired'),
                  validate: value => {
                    const hasUpper = /[A-Z]/.test(value);
                    const hasLower = /[a-z]/.test(value);
                    const hasNumber = /\d/.test(value);
                    const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(value);
                    if (value.length < 8) return t('authRuleMinLength');
                    if (!hasUpper) return t('authRuleUppercase');
                    if (!hasLower) return t('authRuleLowercase');
                    if (!hasNumber) return t('authRuleNumber');
                    if (!hasSpecial) return t('authRuleSpecial');
                    return true;
                  }
                })}
              />
              <button
                type="button"
                onClick={() => togglePassword('new')}
                disabled={loading}
                className="password-toggle-btn"
                aria-label={showPasswords.new ? t('authHideNewPassword') : t('authShowNewPassword')}
              >
                {showPasswords.new ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>

            {newPassword.length > 0 && passwordStrength.level && (
              <p className={`password-strength-indicator ${passwordStrength.level}`}>
                <ShieldCheck size={12} />
                {passwordStrength.label}
              </p>
            )}
            {newPassword.length > 0 && passwordStrength.hint && (
              <p className="password-strength-hint">{passwordStrength.hint}</p>
            )}

            {/* Password Requirements Checklist */}
            {newPassword.length > 0 && (
              <div className="password-requirements mt-2">
                <div className="requirement-item">
                  <span className={`requirement-icon ${hasLength ? 'success' : 'fail'}`}>
                    {hasLength ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span>{t('authChecklistLength')}</span>
                </div>
                <div className="requirement-item">
                  <span className={`requirement-icon ${hasLower && hasUpper ? 'success' : 'fail'}`}>
                    {hasLower && hasUpper ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span>{t('authChecklistCase')}</span>
                </div>
                <div className="requirement-item">
                  <span className={`requirement-icon ${hasNumber ? 'success' : 'fail'}`}>
                    {hasNumber ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span>{t('authChecklistNumber')}</span>
                </div>
                <div className="requirement-item">
                  <span className={`requirement-icon ${hasSpecial ? 'success' : 'fail'}`}>
                    {hasSpecial ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span>{t('authChecklistSpecial')}</span>
                </div>
              </div>
            )}

            {errors.newPassword && (
              <p className="form-error">
                <AlertCircle size={14} />
                {errors.newPassword.message}
              </p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">{t('authConfirmNewPassword')} <span className="text-danger">*</span></label>
            <div className="login-input-wrap">
              <input
                type={showPasswords.confirm ? 'text' : 'password'}
                className={`form-input ${errors.confirmPassword ? 'error' : ''}`}
                placeholder={t('authConfirmNewPasswordPlaceholder')}
                autoComplete="new-password"
                disabled={loading}
                {...register('confirmPassword', {
                  required: t('authConfirmPasswordRequired'),
                  validate: value => value === newPassword || t('authPasswordsDoNotMatch')
                })}
              />
              <button
                type="button"
                onClick={() => togglePassword('confirm')}
                disabled={loading}
                className="password-toggle-btn"
                aria-label={showPasswords.confirm ? t('authHideConfirmPassword') : t('authShowConfirmPassword')}
              >
                {showPasswords.confirm ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {errors.confirmPassword && (
              <p className="form-error">
                <AlertCircle size={14} />
                {errors.confirmPassword.message}
              </p>
            )}
          </div>

          <div className="login-hint">{t('authResetHint')}</div>

          <div className="auth-actions">
            <button 
              type="submit" 
              className="auth-btn auth-btn-primary"
              disabled={loading || !allRulesMet}
            >
              {loading ? t('authResetting') : t('authResetButton')}
            </button>
            <button 
              onClick={() => navigate('/login')}
              className="auth-btn auth-btn-secondary"
              disabled={loading}
            >
              <ArrowLeft size={20} className="mr-2" />
              {t('authBackToLogin')}
            </button>
          </div>
        </form>

        <div className="login-footer">
          <p className="login-support">
            {t('authResetFooter')}
          </p>
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;

