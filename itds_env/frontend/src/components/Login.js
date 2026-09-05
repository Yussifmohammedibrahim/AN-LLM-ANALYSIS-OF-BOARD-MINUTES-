import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useAuth } from '../context/AuthContext';
import { Eye, EyeOff, AlertCircle, ShieldCheck, Lock } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import { notifyError } from '../utils/notify';

// ===== SECURITY UTILITIES =====
const sanitizeInput = (value) => {
  if (typeof value !== 'string') return '';
  return String(value)
    .trim()
    .replace(/[^\w\s.-@]/g, '') // Allow alphanumeric, spaces, dots, hyphens, @
    .slice(0, 128); // Limit length
};

const sanitizeErrorMessage = (message) => {
  if (typeof message !== 'string') return 'An error occurred.';
  // Remove potential script tags, HTML, and suspicious patterns
  return message
    .replace(/<[^>]*>/g, '') // Remove HTML tags
    .replace(/javascript:/gi, '') // Remove javascript: protocol
    .replace(/on\w+=/gi, '') // Remove event handlers
    .slice(0, 200); // Limit length
};

const validatePasswordStrength = (password, t) => {
  if (!password || typeof password !== 'string') {
    return {
      valid: false,
      message: t('loginPasswordRequired'),
      level: 'weak',
      label: t('authPasswordStrengthWeak')
    };
  }

  const checks = [
    { ok: password.length >= 8, message: t('authRuleMinLength') },
    { ok: /[A-Z]/.test(password), message: t('authRuleUppercase') },
    { ok: /[a-z]/.test(password), message: t('authRuleLowercase') },
    { ok: /[0-9]/.test(password), message: t('authRuleNumber') }
  ];

  const score = checks.reduce((acc, item) => acc + (item.ok ? 1 : 0), 0);
  const firstMissing = checks.find((item) => !item.ok);

  if (score === 4) {
    return {
      valid: true,
      message: '',
      level: 'strong',
      label: t('authPasswordStrengthStrong')
    };
  }

  if (score === 3) {
    return {
      valid: false,
      message: firstMissing ? firstMissing.message : t('authPasswordMustMeetRequirements'),
      level: 'medium',
      label: t('authPasswordStrengthMedium')
    };
  }

  return {
    valid: false,
    message: firstMissing ? firstMissing.message : t('authPasswordMustMeetRequirements'),
    level: 'weak',
    label: t('authPasswordStrengthWeak')
  };
};

const validateUsername = (username) => {
  if (!username || typeof username !== 'string') return { valid: false, message: 'Username required' };
  const sanitized = sanitizeInput(username);
  if (sanitized.length < 3) return { valid: false, message: 'Username must be at least 3 characters' };
  if (!/^[a-zA-Z0-9._-]+$/.test(sanitized)) return { valid: false, message: 'Invalid username format' };
  return { valid: true, message: '' };
};

// Rate limiting: Track failed attempts
const MAX_LOGIN_ATTEMPTS = 5;
const LOCKOUT_DURATION_MS = 15 * 60 * 1000; // 15 minutes

const getLoginAttempts = () => {
  try {
    const stored = sessionStorage.getItem('login_attempts');
    return stored ? JSON.parse(stored) : { count: 0, timestamp: null };
  } catch {
    return { count: 0, timestamp: null };
  }
};

const incrementLoginAttempts = () => {
  const attempts = getLoginAttempts();
  const now = Date.now();
  
  if (attempts.timestamp && now - attempts.timestamp > LOCKOUT_DURATION_MS) {
    // Reset if lockout period expired
    sessionStorage.setItem('login_attempts', JSON.stringify({ count: 1, timestamp: now }));
    return { count: 1, isLocked: false };
  }
  
  attempts.count += 1;
  attempts.timestamp = now;
  sessionStorage.setItem('login_attempts', JSON.stringify(attempts));
  return { count: attempts.count, isLocked: attempts.count >= MAX_LOGIN_ATTEMPTS };
};

const resetLoginAttempts = () => {
  sessionStorage.removeItem('login_attempts');
};

const isLoginLocked = () => {
  const attempts = getLoginAttempts();
  const now = Date.now();
  if (!attempts.timestamp) return false;
  if (now - attempts.timestamp > LOCKOUT_DURATION_MS) {
    resetLoginAttempts();
    return false;
  }
  return attempts.count >= MAX_LOGIN_ATTEMPTS;
};

// ===== COMPONENT =====
const Login = () => {
  const { login, loading, error, clearError } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [isAccountLocked, setIsAccountLocked] = useState(false);
  const [lockoutTimeRemaining, setLockoutTimeRemaining] = useState(0);
  const [passwordStrengthMessage, setPasswordStrengthMessage] = useState('');
  const [passwordStrengthLevel, setPasswordStrengthLevel] = useState('');
  const [passwordStrengthLabel, setPasswordStrengthLabel] = useState('');

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch
  } = useForm();

  // Check for account lockout on mount and set up timer
  useEffect(() => {
    const locked = isLoginLocked();
    setIsAccountLocked(locked);
    
    if (locked) {
      const interval = setInterval(() => {
        const attempts = getLoginAttempts();
        const elapsed = Date.now() - attempts.timestamp;
        const remaining = Math.max(0, LOCKOUT_DURATION_MS - elapsed);
        setLockoutTimeRemaining(Math.ceil(remaining / 1000));
        
        if (remaining <= 0) {
          resetLoginAttempts();
          setIsAccountLocked(false);
          clearInterval(interval);
        }
      }, 1000);
      
      return () => clearInterval(interval);
    }
  }, []);

  // Watch password field for strength validation
  const password = watch('password', '');
  useEffect(() => {
    if (password) {
      const validation = validatePasswordStrength(password, t);
      setPasswordStrengthMessage(validation.message);
      setPasswordStrengthLevel(validation.level || 'weak');
      setPasswordStrengthLabel(validation.label || t('authPasswordStrengthWeak'));
    } else {
      setPasswordStrengthMessage('');
      setPasswordStrengthLevel('');
      setPasswordStrengthLabel('');
    }
  }, [password, t]);

  const onSubmit = async (data) => {
    clearError();
    
    // Security Check 1: Account lockout
    if (isLoginLocked()) {
      setIsAccountLocked(true);
      const attempts = getLoginAttempts();
      const remaining = Math.ceil((LOCKOUT_DURATION_MS - (Date.now() - attempts.timestamp)) / 1000);
      setLockoutTimeRemaining(remaining);
      return;
    }

    // Security Check 2: Validate username
    const usernameValidation = validateUsername(data.username);
    if (!usernameValidation.valid) {
      notifyError(usernameValidation.message);
      return;
    }

    // Security Check 3: Validate password strength
    const passwordValidation = validatePasswordStrength(data.password, t);
    if (!passwordValidation.valid) {
      notifyError(passwordValidation.message);
      return;
    }

    try {
      // Sanitize inputs before sending
      const sanitizedUsername = sanitizeInput(data.username);
      
      const payload = {
        username: sanitizedUsername,
        password: data.password, // NEVER sanitize passwords - they're hashed server-side
      };

      const result = await login(payload);
      
        if (result.success) {
        // Reset login attempts on successful login
        resetLoginAttempts();
        setIsAccountLocked(false);
        
        // If the account requires a password change (first-time temporary password),
        // send user to the Change Password flow before granting full access.
        if (result.user?.must_change_password) {
          navigate('/change-password', { replace: true });
        } else if (result.user?.role === 'super_admin') {
          navigate('/super-admin', { replace: true });
        } else {
          navigate('/', { replace: true });
        }
      } else {
        // Increment failures on failed attempt
        const { isLocked } = incrementLoginAttempts();
        if (isLocked) {
          setIsAccountLocked(true);
          setLockoutTimeRemaining(Math.ceil(LOCKOUT_DURATION_MS / 1000));
        }
      }
    } catch (err) {
      // Increment failures on exception
      const { isLocked } = incrementLoginAttempts();
      if (isLocked) {
        setIsAccountLocked(true);
        setLockoutTimeRemaining(Math.ceil(LOCKOUT_DURATION_MS / 1000));
      }
    }
  };

  const lockoutMinutesRemaining = Math.max(1, Math.ceil(lockoutTimeRemaining / 60));

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-container">
            <img src="/ITDS_LOGO.png" alt="ITDS Logo" className="logo-image" />
          </div>
          <h1 className="login-title">Board Minutes Analyzer</h1>
          <p className="login-subtitle">{t('loginSubtitle')}</p>
        </div>

        {/* Account Lockout Warning */}
        {isAccountLocked && (
          <div className="alert alert-warning" role="alert">
            <Lock size={20} />
            <div>
              <strong>Account temporarily locked</strong>
              <p>
                Too many login attempts. Please try again in {lockoutMinutesRemaining}{' '}
                minute{lockoutMinutesRemaining === 1 ? '' : 's'}.
              </p>
            </div>
          </div>
        )}

        {/* Sanitized Error Messages */}
        {error && (
          <div className="alert alert-error" role="alert">
            <AlertCircle size={20} />
            <span>{sanitizeErrorMessage(error)}</span>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="login-form" noValidate>
          <div className="form-group">
            <label className="form-label">{t('loginUsername')}</label>
            <input
              type="text"
              className={`form-input ${errors.username ? 'error' : ''}`}
              placeholder={t('loginUsernamePlaceholder')}
              autoComplete="username"
              disabled={isAccountLocked}
              maxLength="128"
              {...register('username', { 
                required: t('loginUsernameRequired'),
                validate: (value) => {
                  const validation = validateUsername(value);
                  return validation.valid || validation.message;
                }
              })}
            />
            {errors.username && (
              <p className="form-error">
                <AlertCircle size={14} />
                {errors.username.message}
              </p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">{t('loginPassword')}</label>
            <div className="login-input-wrap">
              <input
                type={showPassword ? 'text' : 'password'}
                className={`form-input ${errors.password ? 'error' : ''}`}
                placeholder={t('loginPasswordPlaceholder')}
                autoComplete="current-password"
                disabled={isAccountLocked}
                maxLength="256"
                {...register('password', {
                    required: t('loginPasswordRequired'),
                    // Allow weaker temporary passwords at login so first-time users
                    // can sign in with a temporary password and then change it.
                    // Strong password validation is enforced during change-password flows.
                    validate: (value) => (typeof value === 'string' && value.length > 0) || t('loginPasswordRequired')
                  })}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="password-toggle-btn"
                aria-label={showPassword ? t('loginHidePassword') : t('loginShowPassword')}
                disabled={isAccountLocked}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {errors.password && (
              <p className="form-error">
                <AlertCircle size={14} />
                {errors.password.message}
              </p>
            )}
            {/* Password Strength Indicator */}
            {password && !errors.password && passwordStrengthLevel && (
              <p className={`password-strength-indicator ${passwordStrengthLevel}`}>
                <ShieldCheck size={12} />
                {passwordStrengthLabel}
              </p>
            )}
            {password && !errors.password && passwordStrengthMessage && (
              <p className="password-strength-hint">
                {passwordStrengthMessage}
              </p>
            )}
          </div>

          <div className="auth-actions">
            <button
              type="submit"
              className="auth-btn auth-btn-primary"
              disabled={loading || isAccountLocked}
            >
              <ShieldCheck size={16} />
              {loading ? t('loginSigningIn') : t('loginSignInSecurely')}
            </button>
            <Link 
              to="/forgot-password" 
              className="auth-btn auth-btn-secondary"
              onClick={(e) => isAccountLocked && e.preventDefault()}
            >
              {t('loginForgotPassword')}
            </Link>
          </div>
        </form>

        <div className="login-hint">
          {t('loginHint')}
        </div>

        <div className="login-footer">
          <p className="login-support">
            {t('loginSupport')}
          </p>
          {/* Security Badge */}
          <div className="security-badge">
            <Lock size={14} />
            <span>Secure login with input validation and rate limiting</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;

