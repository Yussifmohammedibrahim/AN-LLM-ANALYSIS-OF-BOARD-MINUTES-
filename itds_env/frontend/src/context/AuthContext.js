import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { authAPI } from '../api/api';
import { notifyError, notifySuccess, notifyWarning } from '../utils/notify';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mustChangePassword, setMustChangePassword] = useState(false);

  const getLoginMetadata = useCallback(async () => {
    // Collect best-effort client metadata for audit logs.
    const meta = {
      device_name: 'Unknown Device',
      platform: (typeof navigator !== 'undefined' && navigator.platform) ? navigator.platform : 'Unknown',
      browser_language: (typeof navigator !== 'undefined' && navigator.language) ? navigator.language : 'unknown',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      client_ip: null,
      location: null,
    };

    if (typeof navigator !== 'undefined') {
      const uaData = navigator.userAgentData;
      if (uaData && Array.isArray(uaData.brands) && uaData.brands.length) {
        const browser = uaData.brands.map((b) => b.brand).join(', ');
        meta.device_name = `${uaData.platform || meta.platform} (${browser})`;
      } else if (navigator.userAgent) {
        meta.device_name = `${meta.platform} (${navigator.userAgent})`;
      }

      // Best-effort public IP lookup.
      const ipPromise = (async () => {
        try {
          const ipResponse = await Promise.race([
            fetch('https://api.ipify.org?format=json', { method: 'GET' }).then((r) => r.json()),
            new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1800)),
          ]);
          if (ipResponse?.ip) {
            meta.client_ip = ipResponse.ip;
            return;
          }
        } catch {
          // Fallback service below.
        }

        try {
          const altResponse = await Promise.race([
            fetch('https://icanhazip.com/', { method: 'GET' }).then((r) => r.text()),
            new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1200)),
          ]);
          const ip = String(altResponse || '').trim();
          if (ip) meta.client_ip = ip;
        } catch {
          // Keep null if unavailable.
        }
      })();

      // Best-effort geolocation for coordinates in recent activity.
      const geoPromise = (async () => {
        if (!navigator.geolocation) return;
        try {
          const pos = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
              enableHighAccuracy: true,
              timeout: 2500,
              maximumAge: 60000,
            });
          });
          if (pos?.coords) {
            meta.location = {
              latitude: Number(pos.coords.latitude.toFixed(6)),
              longitude: Number(pos.coords.longitude.toFixed(6)),
              accuracy_m: Math.round(pos.coords.accuracy || 0),
              captured_at: new Date().toISOString(),
            };
          }
        } catch {
          // Permission denied or timeout; leave null.
        }
      })();

      await Promise.allSettled([ipPromise, geoPromise]);
    }

    return meta;
  }, []);

  // Initialize auth state from localStorage - OPTIMIZED for speed
  useEffect(() => {
  const initAuth = async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      console.log('No auth token found');
      setLoading(false);
      return;
    }

    const userData = JSON.parse(localStorage.getItem('user') || 'null');
    
    // Fast path: Load cached user immediately
    if (userData && userData.user_id) {
      setUser(userData);
      setMustChangePassword(userData.must_change_password || false);
      setLoading(false);
    } else {
      setLoading(false);
      return;
    }

    // Background validation: Validate with API asynchronously WITHOUT blocking
    try {
      const response = await authAPI.getCurrentUser();
      setUser(response.data);
      setMustChangePassword(response.data.must_change_password || false);
      console.log('User re-validated:', response.data.username);
    } catch (err) {
      console.warn('Background validation failed:', err.message, '- using cached data');
    }
  };

  initAuth();
}, []);

  // Token refresh timer ref
  const refreshTimerRef = useRef(null);

  // Helper: parse JWT and return payload or null
  const parseJwt = useCallback((token) => {
    if (!token) return null;
    try {
      const parts = token.split('.');
      if (parts.length < 2) return null;
      const payload = parts[1];
      // atob may need padding
      const padded = payload.padEnd(payload.length + (4 - (payload.length % 4)) % 4, '=');
      const decoded = JSON.parse(atob(padded));
      return decoded;
    } catch (e) {
      return null;
    }
  }, []);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleTokenRefresh = useCallback((accessToken) => {
    clearRefreshTimer();
    const payload = parseJwt(accessToken);
    if (!payload || !payload.exp) return;
    const expiresAtMs = payload.exp * 1000;
    const nowMs = Date.now();
    // Refresh 60 seconds before expiry (or at half the TTL if very short)
    let refreshAt = expiresAtMs - 60000;
    if (refreshAt - nowMs <= 0) {
      // Token near expiry, refresh in 2 seconds
      refreshAt = nowMs + 2000;
    }
    const delay = Math.max(0, refreshAt - nowMs);
    refreshTimerRef.current = setTimeout(async () => {
      try {
        const resp = await authAPI.refresh();
        // Server returns { access_token } and sets rotated refresh cookie
        const newAccess = resp.data?.access_token;
        if (newAccess) {
          localStorage.setItem('token', newAccess);
          // Reschedule next refresh
          scheduleTokenRefresh(newAccess);
        }
      } catch (err) {
        console.error('Auto refresh failed:', err);
        // Clear and force logout on persistent failures
        clearRefreshTimer();
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        setUser(null);
        window.location.href = '/login';
      }
    }, delay);
  }, [parseJwt, clearRefreshTimer]);

  // Login
  const login = useCallback(async (credentials) => {
    setError(null);
    setLoading(true);

    try {
      const loginMeta = await getLoginMetadata();
      const response = await authAPI.login({
        ...credentials,
        client_metadata: loginMeta,
      });
      const { access_token, must_change_password, ...userData } = response.data;
      userData.must_change_password = must_change_password;

      // Store in localStorage
      localStorage.setItem('token', access_token);
      // Schedule automatic refresh using server-set HttpOnly refresh cookie
      scheduleTokenRefresh(access_token);
      localStorage.setItem('user', JSON.stringify(userData));

      setUser(userData);
      setMustChangePassword(must_change_password || false);
      notifySuccess('Login successful. Welcome back.');
      return { success: true, user: userData };
    } catch (err) {
      const message = err.response?.data?.error || 'Login failed. Please try again.';
      setError(message);
      notifyError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  }, [getLoginMetadata, scheduleTokenRefresh]);

  // Logout
  const logout = useCallback(async () => {
    let remoteLogoutFailed = false;
    try {
      const logoutMeta = await getLoginMetadata();
      // Send logout request; server will clear refresh cookie
      await authAPI.logout({ client_metadata: logoutMeta });
    } catch (err) {
      // Ignore logout errors
      remoteLogoutFailed = true;
      console.error('Logout error:', err);
    } finally {
      // Clear client state and refresh timer
      clearRefreshTimer();
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      setUser(null);
      if (remoteLogoutFailed) {
        notifyWarning('Logout completed locally, but remote session cleanup failed.');
      } else {
        notifySuccess('Logout successful. See you next time.');
      }
    }
  }, [getLoginMetadata, clearRefreshTimer]);

  // Change password
  const changePassword = useCallback(async (data) => {
    setError(null);

    try {
      const response = await authAPI.changePassword(data);
      const refreshed = await authAPI.getCurrentUser();
      setUser(refreshed.data);
      setMustChangePassword(refreshed.data.must_change_password || false);
      localStorage.setItem('user', JSON.stringify(refreshed.data));
      return { success: true, message: response.data.message };
    } catch (err) {
      const message = err.response?.data?.error || 'Password change failed.';
      setError(message);
      return { success: false, error: message };
    }
  }, []);

  // Update user profile
  const updateProfile = useCallback(async (data) => {
    setError(null);

    try {
      const response = await authAPI.updateUser(user.id, data);
      const updatedUser = { ...user, ...response.data };
      localStorage.setItem('user', JSON.stringify(updatedUser));
      setUser(updatedUser);
      return { success: true };
    } catch (err) {
      const message = err.response?.data?.error || 'Profile update failed.';
      setError(message);
      return { success: false, error: message };
    }
  }, [user]);

  // Check if user has role
  const hasRole = useCallback((roles) => {
    if (!user) return false;
    if (typeof roles === 'string') {
      return user.role === roles;
    }
    return roles.includes(user.role);
  }, [user]);

  // Check if user is admin
  const isAdmin = useCallback(() => {
    return ['admin', 'super_admin'].includes(user?.role);
  }, [user]);

  const isSuperAdmin = useCallback(() => {
    return user?.role === 'super_admin';
  }, [user]);

  // Refresh user profile from API
  const refreshUser = useCallback(async () => {
    try {
      const response = await authAPI.getCurrentUser();
      const updatedData = response.data;
      setUser(updatedData);
      setMustChangePassword(updatedData.must_change_password || false);
      localStorage.setItem('user', JSON.stringify(updatedData));
      return updatedData;
    } catch (err) {
      console.error('Failed to refresh user:', err);
      return null;
    }
  }, []);

  // When component unmounts, clear any timers
  useEffect(() => {
    return () => clearRefreshTimer();
  }, [clearRefreshTimer]);

  // Check if user is authenticated
  const isAuthenticated = useCallback(() => {
    return !!user && !!localStorage.getItem('token');
  }, [user]);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Value object
  const value = {
    user,
    mustChangePassword,
    loading,
    error,
    login,
    logout,
    changePassword,
    updateProfile,
    hasRole,
    isAdmin,
    isSuperAdmin,
    isAuthenticated,
    isPasswordChangeRequired: () => mustChangePassword,
    refreshUser,
    clearError
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;