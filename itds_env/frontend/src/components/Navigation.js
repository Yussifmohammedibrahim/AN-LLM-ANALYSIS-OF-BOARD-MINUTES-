import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { useAuth } from '../context/AuthContext';
import {
  Settings, LogOut, Menu, X, User, Key, FileText, Wrench, Bell, ArrowRight, CalendarDays, Search
} from 'lucide-react';
import DynamicIcon from './DynamicIcon';
import { notificationsAPI } from '../api/api';
import api from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';
import { useConfirm } from './ConfirmProvider';

const Navigation = ({ user, setShowUploadModal }) => {
  const { logout, isAdmin } = useAuth();
  const { t } = useLanguage();
  const confirm = useConfirm();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notificationMenuOpen, setNotificationMenuOpen] = useState(false);
  const [recentNotifications, setRecentNotifications] = useState([]);
  const [notificationCount, setNotificationCount] = useState(0);
  const [notificationSummary, setNotificationSummary] = useState({ unread: 0, email: 0, push: 0 });
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const [badgePulse, setBadgePulse] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [topbarUtilitiesHost, setTopbarUtilitiesHost] = useState(null);
  const [navLoading, setNavLoading] = useState(false);
  const [navLoadingLabel, setNavLoadingLabel] = useState('');
  const [reportsScheduleEnabled, setReportsScheduleEnabled] = useState(false);
  const notificationAnchorRef = useRef(null);
  const userMenuAnchorRef = useRef(null);
  const previousUnreadRef = useRef(0);

  const refreshNotificationSummary = useCallback(async () => {
    if (!user) {
      setNotificationCount(0);
      setNotificationSummary({ unread: 0, email: 0, push: 0 });
      return;
    }

    const response = await notificationsAPI.getSummary({ _ts: Date.now() });
    const unread = Number(response.data?.unread || 0);
    const email = Number(response.data?.email || 0);
    const push = Number(response.data?.push || 0);

    setNotificationCount(unread);
    setNotificationSummary({ unread, email, push });
    setLastUpdatedAt(new Date());

    if (unread > previousUnreadRef.current) {
      setBadgePulse(true);
      window.setTimeout(() => setBadgePulse(false), 1200);
    }
    previousUnreadRef.current = unread;
  }, [user]);

  const formatUpdatedLabel = (value) => {
    if (!value) return t('navLastUpdatedJustNow');
    try {
      return `${t('navLastUpdated')} ${value.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } catch {
      return t('navLastUpdatedRecently');
    }
  };

  const loadRecentNotifications = useCallback(async () => {
    if (!user) {
      setRecentNotifications([]);
      return;
    }
    const response = await notificationsAPI.getNotifications({ limit: 5, _ts: Date.now() });
    setRecentNotifications(response.data?.items || []);
  }, [user]);

  useEffect(() => {
    let active = true;

    const loadNotificationCount = async () => {
      try {
        await refreshNotificationSummary();
      } catch {
        if (active) {
          setNotificationCount(0);
          setNotificationSummary({ unread: 0, email: 0, push: 0 });
        }
      }
    };

    loadNotificationCount();
    const intervalId = window.setInterval(loadNotificationCount, 60000);

    // Also load scheduled reports status for nav badge
    const loadScheduleStatus = async () => {
      if (!['editor', 'admin', 'super_admin'].includes(user?.role)) {
        if (active) setReportsScheduleEnabled(false);
        return;
      }
      try {
        const resp = await api.get('/api/user/settings/report-schedules');
        const schedule = resp.data?.schedule || null;
        if (active && schedule) setReportsScheduleEnabled(Boolean(schedule.enabled));
      } catch (err) {
        // ignore - feature optional
      }
    };
    loadScheduleStatus();
    const scheduleInterval = window.setInterval(loadScheduleStatus, 60000);

    // Listen for immediate updates when Settings saves
    const onScheduleUpdated = () => { loadScheduleStatus(); };
    window.addEventListener('report-schedule-updated', onScheduleUpdated);

    const handleDocumentClick = (event) => {
      if (notificationAnchorRef.current && !notificationAnchorRef.current.contains(event.target)) {
        setNotificationMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleDocumentClick);

    return () => {
      active = false;
      window.clearInterval(intervalId);
      window.clearInterval(scheduleInterval);
      window.removeEventListener('report-schedule-updated', onScheduleUpdated);
      document.removeEventListener('mousedown', handleDocumentClick);
    };
  }, [user, refreshNotificationSummary]);

  useEffect(() => {
    let active = true;

    const loadRecent = async () => {
      if (!notificationMenuOpen || !user) return;
      try {
        await loadRecentNotifications();
        await refreshNotificationSummary();
        if (active) {
          // no-op; state set in helpers
        }
      } catch {
        if (active) {
          setRecentNotifications([]);
        }
      }
    };

    loadRecent();

    return () => {
      active = false;
    };
  }, [notificationMenuOpen, user, loadRecentNotifications, refreshNotificationSummary]);

  useEffect(() => {
    if (!userMenuOpen) return undefined;

    const handleOutsideClick = (event) => {
      if (userMenuAnchorRef.current && !userMenuAnchorRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [userMenuOpen]);

  useEffect(() => {
    setMobileMenuOpen(false);
    setUserMenuOpen(false);
    setNotificationMenuOpen(false);
  }, [location.pathname]);

  // Keep root `.app` class in sync for responsive sidebar open state and lock body scrolling
  useEffect(() => {
    const root = document.querySelector('.app');
    if (!root) return;
    if (mobileMenuOpen) {
      root.classList.add('sidebar-open');
      // prevent background scroll when mobile panel is open
      document.body.style.overflow = 'hidden';
    } else {
      root.classList.remove('sidebar-open');
      document.body.style.overflow = '';
    }

    return () => {
      if (root) root.classList.remove('sidebar-open');
      document.body.style.overflow = '';
    };
  }, [mobileMenuOpen]);

  useEffect(() => {
    setTopbarUtilitiesHost(document.getElementById('topbar-nav-utilities'));
  }, []);

  const handleMarkAllRead = async () => {
    setMarkingAllRead(true);
    try {
      await notificationsAPI.markAllAsRead();
      notifySuccess('All notifications marked as read.');
      await refreshNotificationSummary();
      await loadRecentNotifications();
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to mark notifications as read.');
    } finally {
      setMarkingAllRead(false);
    }
  };

  const handleLogout = async () => {
    try {
      const result = await confirm({
        title: t('navLogoutConfirmTitle') || t('navLogout'),
        message: t('navLogoutConfirm') || 'Are you sure you want to logout?',
        actions: [
          { label: t('navLogout') || 'Logout', value: 'logout', variant: 'danger' }
        ],
        cancelLabel: t('cancel') || 'Cancel'
      });
      if (result && result.action === 'logout') {
        await logout();
        navigate('/login');
      }
    } catch (err) {
      // If hook not available or cancelled, do nothing
    }
  };

  const handleNavClick = (path, label = '', options = {}) => {
    if (path && location.pathname !== path) {
      setNavLoading(true);
      setNavLoadingLabel(label || 'data');
    }

    if (options.closeMobile) setMobileMenuOpen(false);
    if (options.closeUser) setUserMenuOpen(false);
    if (options.closeNotification) setNotificationMenuOpen(false);
  };

  useEffect(() => {
    if (!navLoading) return;

    // Fail-safe so overlay never gets stuck if a route update is blocked.
    const timeoutId = window.setTimeout(() => {
      setNavLoading(false);
    }, 3000);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [navLoading]);

  useEffect(() => {
    if (navLoading) {
      setNavLoading(false);
    }
  }, [location.pathname, navLoading]);

  const navItems = [
    { path: '/', label: t('navDashboard'), iconName: 'LayoutDashboard' },
    { path: '/super-admin', label: t('navSuperAdmin'), iconName: 'ShieldCheck', roles: ['super_admin'] },
    { path: '/charts', label: t('navCharts'), iconName: 'BarChart2' },
    { path: '/search', label: t('navSearch'), iconName: 'Search' },
    { path: '/reports', label: t('navReports'), iconName: 'FileText', roles: ['viewer', 'editor', 'admin', 'super_admin'] },
    { path: '/reports/analytics', label: 'Analytics', iconName: 'TrendingUp', roles: ['viewer', 'editor', 'admin', 'super_admin'] },
    { path: '/upload', label: t('navUpload'), iconName: 'UploadCloud', roles: ['admin', 'super_admin', 'editor'] },
    { path: '/users', label: t('navUsers'), iconName: 'Users2', roles: ['admin', 'super_admin'] },
    { path: '/activity', label: t('navActivityLogins'), iconName: 'Clock', roles: ['admin', 'super_admin'] },
    { path: '/voice', label: t('navVoiceRecord'), iconName: 'Volume2', roles: ['admin', 'super_admin', 'editor'] },
    { path: '/text-simplification', label: t('navTextSimplify'), iconName: 'Sparkles', roles: ['admin', 'super_admin', 'editor'] },
    { path: '/trend-analysis', label: 'Trends', iconName: 'LineChart', roles: ['admin', 'super_admin'] }
  ];


  const filteredNavItems = navItems.filter(item => {
    if (!item.roles) return true;
    return item.roles.includes(user?.role);
  });

  const isActive = (path) => {
    if (path === '/') {
      return location.pathname === '/' || location.pathname === '/dashboard';
    }
    return location.pathname.startsWith(path);
  };

  const API_BASE_URL = process.env.REACT_APP_API_URL || `http://${window.location.hostname}:5001`;
  const profileImageUrl = user?.profile_image ? `${API_BASE_URL}/uploads/profile_images/${user.profile_image}?t=${Date.now()}` : null;
  const userSectionContent = (
    <div className="user-section">
      <div className="sidebar-quick-actions">
        <Link
          to="/search"
          onClick={() => handleNavClick('/search', t('navSearch'))}
          className={`nav-link hide-mobile ${isActive('/search') ? 'active' : ''}`}
          title={t('navSearch')}
        >
          <Search size={18} />
        </Link>

        {/* Settings Link */}
        <div className="nav-notification-anchor" ref={notificationAnchorRef}>
          <button
            type="button"
            className={`nav-link hide-mobile nav-notification-button ${isActive('/notifications') ? 'active' : ''}`}
            title={t('navNotifications')}
            onClick={() => setNotificationMenuOpen((open) => !open)}
          >
            <Bell size={18} />
            {notificationCount > 0 && (
              <span className={`nav-notification-badge ${badgePulse ? 'pulse' : ''}`}>
                {notificationCount > 99 ? '99+' : notificationCount}
              </span>
            )}
          </button>

          {notificationMenuOpen && (
            <>
              <div className="nav-notification-backdrop" onClick={() => setNotificationMenuOpen(false)} />
              <div className="nav-notification-popover">
                <div className="nav-notification-header">
                  <div>
                    <div className="nav-notification-title">{t('navNotifications')}</div>
                    <div className="nav-notification-subtitle">{t('navRecentAppEvents')}</div>
                    <div className="nav-notification-updated">{formatUpdatedLabel(lastUpdatedAt)}</div>
                    <div className="nav-notification-breakdown">
                      <span className="nav-notification-pill email">Email {notificationSummary.email}</span>
                      <span className="nav-notification-pill push">Push {notificationSummary.push}</span>
                    </div>
                  </div>
                  <div className="nav-notification-actions">
                    <button
                      type="button"
                      className="btn btn-outline btn-sm nav-notification-markall"
                      onClick={handleMarkAllRead}
                      disabled={markingAllRead || notificationSummary.unread === 0}
                    >
                      {markingAllRead ? t('navMarking') : t('navMarkAllRead')}
                    </button>
                    <Link
                      to="/notifications"
                      className="nav-notification-viewall"
                      onClick={() => handleNavClick('/notifications', t('navNotifications'), { closeNotification: true })}
                    >
                      {t('navViewAll')} <ArrowRight size={14} />
                    </Link>
                  </div>
                </div>

                <div className="nav-notification-list">
                  {recentNotifications.length === 0 ? (
                    <div className="nav-notification-empty">{t('navNoRecentNotifications')}</div>
                  ) : recentNotifications.map((item) => (
                    <Link
                      key={item.notification_id}
                      to="/notifications"
                      onClick={() => handleNavClick('/notifications', t('navNotifications'), { closeNotification: true })}
                      className={`nav-notification-item ${item.is_read ? '' : 'unread'}`}
                    >
                      <div className="nav-notification-item-top">
                        <span className={`nav-notification-pill ${item.channel === 'push' ? 'push' : 'email'}`}>
                          {String(item.channel || 'mail').toUpperCase()}
                        </span>
                        <span className={`nav-notification-pill status-${String(item.status || 'sent').toLowerCase()}`}>
                          {String(item.status || 'sent').toUpperCase()}
                        </span>
                      </div>
                      <div className="nav-notification-item-title">{item.title}</div>
                      <div className="nav-notification-item-body">{item.body || t('navOpenNotificationCenterForDetails')}</div>
                    </Link>
                  ))}
                </div>
              </div>
            </>
          )}

        </div>

      </div>

      {/* User Menu */}
      <div className="user-menu-anchor" ref={userMenuAnchorRef}>
        <div
          className="sidebar-profile-summary"
          onClick={() => setUserMenuOpen(!userMenuOpen)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              setUserMenuOpen((open) => !open);
            }
          }}
        >
          <div className="user-avatar">
            {user?.profile_image && profileImageUrl ? (
              <img
                src={profileImageUrl}
                alt={user.username}
                className="user-avatar-image"
                onError={(e) => {
                  console.warn('Profile image load failed', e.target.src);
                  e.target.style.display = 'none';
                  const fallback = e.target.nextSibling;
                  if (fallback) fallback.style.display = 'flex';
                }}
              />
            ) : null}
            <div
              className={`user-avatar-fallback ${user?.profile_image ? 'hidden' : ''}`}
            >
              {user?.username?.charAt(0)?.toUpperCase()}
            </div>
          </div>
          <div className="sidebar-profile-copy hide-mobile">
            <span className="sidebar-profile-name">{user?.username || t('navProfileSettings')}</span>
            <span className="sidebar-profile-role">{String(user?.role || '').replace('_', ' ')}</span>
          </div>
        </div>

        {userMenuOpen && (
          <>
            <div className="user-menu-backdrop" onClick={() => setUserMenuOpen(false)} />
            <div
              className="user-menu-panel"
            >
              <div className="user-menu-header">
                <div className="user-menu-name">{user?.username}</div>
                <div className="user-menu-email">
                  {user?.email || t('navNoEmail')}
                </div>
                <div className="user-menu-role">
                  {user?.role}
                </div>
              </div>
              <div className="user-menu-items">
                <Link
                  to="/settings"
                    onClick={() => handleNavClick('/settings', t('navSettings'), { closeUser: true })}
                  className="user-menu-item"
                >
                  <User size={16} />
                  {t('navProfileSettings')}
                </Link>
                {isAdmin() && (
                  <Link
                    to="/admin-tools"
                    onClick={() => handleNavClick('/admin-tools', t('navAdminTools'), { closeUser: true })}
                    className="user-menu-item"
                  >
                    <Wrench size={16} />
                    {t('navAdminTools')}
                  </Link>
                )}
                <Link
                  to="/change-password"
                    onClick={() => handleNavClick('/change-password', t('navChangePassword'), { closeUser: true })}
                  className="user-menu-item"
                >
                  <Key size={16} />
                  {t('navChangePassword')}
                </Link>
                {isAdmin() && (
                  <Link
                    to="/events"
                    onClick={() => handleNavClick('/events', t('navEvents'), { closeUser: true })}
                    className="user-menu-item"
                  >
                    <CalendarDays size={16} />
                    {t('navManageEvents')}
                  </Link>
                )}
                <button
                  onClick={() => {
                    setUserMenuOpen(false);
                    setShowUploadModal(true);
                  }}
                  className="user-menu-item profile-upload-item"
                >
                  <FileText size={16} />
                  {t('navUploadProfileImage')}
                </button>

                <button
                  onClick={handleLogout}
                  className="user-menu-item logout-item"
                >
                  <LogOut size={16} />
                  {t('navLogout')}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );

  return (
    <nav className="navbar">
      {/* Logo */}
      <Link to="/" className="navbar-brand">
        <img src="/ITDS.jpg" alt="ITDS Logo" className="nav-logo" />
        Board Minutes
      </Link>

      {/* Desktop Navigation */}
      <div className="navbar-menu hide-mobile">
        {filteredNavItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            onClick={() => handleNavClick(item.path, item.label)}
            className={`nav-link ${item.path === '/trend-analysis' ? 'nav-link-trends' : ''} ${isActive(item.path) ? 'active' : ''}`}
          >
            <DynamicIcon name={item.iconName} size={18} />
            {item.label}
            {item.path === '/reports' && reportsScheduleEnabled && (
              <span className="nav-schedule-badge" title="Scheduled reports enabled">•</span>
            )}
          </Link>
        ))}
      </div>

      {topbarUtilitiesHost ? createPortal(userSectionContent, topbarUtilitiesHost) : userSectionContent}

      {/* Mobile Menu Toggle */}
        <button
          type="button"
          className="btn btn-ghost btn-icon hide-desktop"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label={mobileMenuOpen ? t('navCloseMenu') : t('navOpenMenu')}
          aria-expanded={mobileMenuOpen}
          aria-controls="mobile-navigation-menu"
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div
          className="mobile-menu-overlay"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            id="mobile-navigation-menu"
            className="mobile-menu-panel"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={t('navOpenMenu')}
          >
            <div className="mobile-menu-header">
              <div className="mobile-menu-name">{user?.username}</div>
              <div className="mobile-menu-email">
                {user?.email || t('navNoEmail')}
              </div>
              <div className="mobile-menu-role">
                {user?.role}
              </div>
            </div>

            {filteredNavItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => handleNavClick(item.path, item.label, { closeMobile: true })}
                className={`nav-link mobile-menu-link ${isActive(item.path) ? 'active' : ''}`}
              >
                <DynamicIcon name={item.iconName} size={18} />
                {item.label}
              </Link>
            ))}

            <Link
              to="/notifications"
              onClick={() => handleNavClick('/notifications', t('navNotifications'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/notifications') ? 'active' : ''}`}
            >
              <Bell size={18} />
              {t('navNotifications')}{notificationCount > 0 ? ` (${notificationCount})` : ''}
            </Link>

            <Link
              to="/settings"
              onClick={() => handleNavClick('/settings', t('navSettings'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/settings') ? 'active' : ''}`}
            >
              <Settings size={18} />
              {t('navSettings')}
            </Link>

            {isAdmin() && (
              <Link
                to="/admin-tools"
                onClick={() => handleNavClick('/admin-tools', t('navAdminTools'), { closeMobile: true })}
                className={`nav-link mobile-menu-link ${isActive('/admin-tools') ? 'active' : ''}`}
              >
                <Wrench size={18} />
                {t('navAdminTools')}
              </Link>
            )}

            <Link
              to="/change-password"
              onClick={() => handleNavClick('/change-password', t('navChangePassword'), { closeMobile: true })}
              className={`nav-link mobile-menu-link ${isActive('/change-password') ? 'active' : ''}`}
            >
              <Key size={18} />
              {t('navChangePassword')}
            </Link>

            <button
              onClick={handleLogout}
              className="nav-link mobile-menu-logout"
            >
              <LogOut size={18} />
              {t('navLogout')}
            </button>
          </div>
        </div>
      )}

      {navLoading && (
        <div className="nav-transition-overlay" role="status" aria-live="polite">
          <div className="nav-transition-content">
            <div className="nav-transition-spinner" />
            <p className="nav-transition-text">Loading {navLoadingLabel} data...</p>
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navigation;
