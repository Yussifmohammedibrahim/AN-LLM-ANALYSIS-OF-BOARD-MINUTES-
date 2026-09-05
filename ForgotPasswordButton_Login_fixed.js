import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useAuth } from '../context/AuthContext';
import { FileText, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { toast } from 'react-toastify';

const Login = () => {
  const { login, loading, error, clearError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);

  const from = location.state?.from?.pathname || '/dashboard';

  const {
    register,
    handleSubmit,
    formState: { errors }
  } = useForm();

  const onSubmit = async (data) => {
    console.log('Login attempt:', data);
    clearError();
    const result = await login(data);
    console.log('Login result:', result);
    
    if (result.success) {
      navigate(from, { replace: true });
    } else {
      toast.error(result.error || 'Login failed');
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">
            <FileText size={32} />
          </div>
          <h1 className="login-title">ITDS Board Minutes</h1>
          <p className="login-subtitle">Sign in to access the analysis system</p>
        </div>

        {error && (
          <div className="alert alert-error">
            <AlertCircle size={20} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="form-group">
            <label className="form-label">Username</label>
            <input
              type="text"
              className={`form-input ${errors.username ? 'error' : ''}`}
              placeholder="Enter your username"
              {...register('username', { 
                required: 'Username is required' 
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
            <label className="form-label">Password</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                className={`form-input ${errors.password ? 'error' : ''}`}
                placeholder="Enter your password"
                style={{ paddingRight: '3rem' }}
                {...register('password', { 
                  required: 'Password is required' 
                })}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '1rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                  padding: '0.25rem'
                }}
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
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg w-full mt-2"
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="login-footer">
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Contact your administrator for access
          </p>
        </div>

        {/* Forgot Password Button */}
        <div className="text-center mt-6">
          <Link 
            to="/forgot-password" 
            className="forgot-password-link inline-block text-blue-500 hover:text-blue-700 text-sm font-medium transition-colors"
          >
            Forgot Password
          </Link>
        </div>
      </div>
    </div>
  );
};

export default Login;

