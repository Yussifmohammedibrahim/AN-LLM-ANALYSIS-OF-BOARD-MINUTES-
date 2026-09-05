import React, { useState, useEffect, useContext } from 'react';
import api, { aiAPI } from '../api/api';
import AuthContext from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { notifyError, notifySuccess } from '../utils/notify';
import { applyThemeMode, getStoredThemeMode, THEME_DARK } from '../utils/theme';

const urlBase64ToUint8Array = (base64String) => {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
};

const createEmptyReportSchedule = () => ({
  enabled: false,
  cadence: 'weekly',
  deliveryDate: '',
  deliveryTime: '08:00',
  recipients: '',
  theme: '',
  sentiment: 'all',
  lastDeliveryStatus: null,
  lastDeliveryError: null,
  lastDeliveryAt: null
});

const Settings = () => {
  const { user } = useContext(AuthContext);
  const { t, changeLanguage } = useLanguage();
  const isSuperAdmin = user?.role === 'super_admin';
  const canAccessAdminSettings = ['admin', 'super_admin'].includes(user?.role);
  const canManageReportDelivery = ['editor', 'admin', 'super_admin'].includes(user?.role);
  const [settings, setSettings] = useState({
    darkMode: getStoredThemeMode() === THEME_DARK,
    notifications: true,
    emailAlerts: false,
    anomalyEmailAlerts: true,
    language: 'en',
    pushPermission: 'default'
  });
  const [loading, setLoading] = useState(false);
  const [savingReportSchedule, setSavingReportSchedule] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [sendingTestEmail, setSendingTestEmail] = useState(false);
  const [sendingTestPush, setSendingTestPush] = useState(false);
  const [sendingSystemAlert, setSendingSystemAlert] = useState(false);
  const [isSystemAlertOpen, setIsSystemAlertOpen] = useState(false);
  const [reportSchedule, setReportSchedule] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('reportScheduleSettings') || 'null') || createEmptyReportSchedule();
    } catch {
      return createEmptyReportSchedule();
    }
  });
  const [themes, setThemes] = useState([]);
  const [adminSchedules, setAdminSchedules] = useState([]);
  const [systemAlert, setSystemAlert] = useState({
    title: 'System Status Update',
    message: '',
    severity: 'info'
  });

  
  useEffect(() => {
    // Load settings from localStorage
    const savedSettings = localStorage.getItem('appSettings');
    if (savedSettings) {
      const parsed = JSON.parse(savedSettings);
      setSettings(parsed);
      // Apply dark mode on initial load
      applyThemeMode(parsed.darkMode ? 'dark' : 'light');
      if (parsed.language) {
        changeLanguage(parsed.language);
      }
    }
  }, [changeLanguage]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.hash !== '#report-schedule-settings') return;
    const target = document.getElementById('report-schedule-settings');
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  useEffect(() => {
    if (!canManageReportDelivery) {
      return;
    }

    let mounted = true;

    const loadReportSchedule = async () => {
      try {
        const response = await api.get('/api/user/settings/report-schedules');
        if (!mounted) return;
        const schedule = response.data?.schedule || {};
        let filters = {};
        try {
          filters = schedule.filters_json
            ? (typeof schedule.filters_json === 'string' ? JSON.parse(schedule.filters_json) : schedule.filters_json)
            : {};
        } catch {
          filters = {};
        }
        const nextSchedule = {
          enabled: Boolean(schedule.enabled),
          cadence: schedule.cadence || 'weekly',
          deliveryDate: schedule.delivery_date || '',
          deliveryTime: schedule.delivery_time || '08:00',
          recipients: schedule.recipient_emails || '',
          theme: filters.theme || '',
          sentiment: filters.sentiment || 'all',
          lastDeliveryStatus: schedule.last_delivery_status || null,
          lastDeliveryError: schedule.last_delivery_error || null,
          lastDeliveryAt: schedule.last_delivery_at || null
        };
        setReportSchedule(nextSchedule);
        localStorage.setItem('reportScheduleSettings', JSON.stringify(nextSchedule));
      } catch (error) {
        console.warn('Unable to load report schedules from backend:', error);
      }
    };

    loadReportSchedule();

    // load available themes for dropdown
    const loadThemes = async () => {
      try {
        const resp = await aiAPI.getDynamicThemes();
        const extracted = resp.data?.themes || [];
        // normalize to simple array of strings
        const unique = Array.isArray(extracted) ? Array.from(new Set(extracted.map(t => (typeof t === 'string' ? t : (t.name || ''))).filter(Boolean))) : [];
        if (mounted) setThemes(unique);
      } catch (err) {
        console.warn('Could not load themes for settings:', err?.message || err);
      }
    };

    loadThemes();

    // Load admin schedules for super-admins
    const loadAdminSchedules = async () => {
      if (!isSuperAdmin) return;
      try {
        const resp = await api.get('/api/admin/report-schedules?include_deleted=true&limit=500');
        setAdminSchedules(resp.data?.schedules || []);
      } catch (err) {
        console.warn('Could not load admin schedules:', err?.message || err);
      }
    };

    loadAdminSchedules();

    return () => {
      mounted = false;
    };
  }, [canManageReportDelivery, isSuperAdmin]);

  useEffect(() => {
    let mounted = true;

    const loadNotificationSettings = async () => {
      try {
        const response = await api.get('/api/user/settings/notifications');
        const remote = response.data || {};

        if (!mounted) {
          return;
        }

        setSettings((prev) => {
          const merged = {
            ...prev,
            notifications: Boolean(remote.notifications),
            emailAlerts: Boolean(remote.emailAlerts),
            anomalyEmailAlerts: typeof remote.anomalyEmailAlerts !== 'undefined' ? Boolean(remote.anomalyEmailAlerts) : Boolean(prev.anomalyEmailAlerts),
            pushPermission: remote.pushPermission || 'default'
          };
          localStorage.setItem('appSettings', JSON.stringify(merged));
          return merged;
        });
      } catch (error) {
        // Keep local values if backend settings are temporarily unavailable.
        console.warn('Unable to load notification settings from backend:', error);
      }
    };

    loadNotificationSettings();

    return () => {
      mounted = false;
    };
  }, []);

  const persistNotificationSettings = async (updates, successMessage = 'Settings updated successfully.') => {
    const previous = settings;
    const optimistic = { ...settings, ...updates };

    setSettings(optimistic);
    localStorage.setItem('appSettings', JSON.stringify(optimistic));
    setSavingSettings(true);

    try {
      const response = await api.put('/api/user/settings/notifications', updates);
      const serverSettings = response.data?.settings || updates;
      const finalized = { ...optimistic, ...serverSettings };
      setSettings(finalized);
      localStorage.setItem('appSettings', JSON.stringify(finalized));
      notifySuccess(successMessage);
    } catch (error) {
      setSettings(previous);
      localStorage.setItem('appSettings', JSON.stringify(previous));
      notifyError(error.response?.data?.error || 'Failed to save notification settings.');
      throw error;
    } finally {
      setSavingSettings(false);
    }
  };

  const registerPushSubscription = async () => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      throw new Error('Push notifications are not supported in this browser.');
    }

    const keyResponse = await api.get('/api/user/settings/notifications/push/public-key');
    const publicKey = keyResponse.data?.publicKey;
    if (!publicKey) {
      throw new Error('Push key is unavailable on the server.');
    }

    const registration = await navigator.serviceWorker.register('/notification-sw.js');
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
      });
    }

    await api.post('/api/user/settings/notifications/push/subscription', {
      endpoint: subscription.endpoint,
      keys: {
        p256dh: subscription.toJSON()?.keys?.p256dh,
        auth: subscription.toJSON()?.keys?.auth
      },
      contentEncoding: 'aes128gcm'
    });

    return subscription;
  };

  const unregisterPushSubscription = async () => {
    if (!('serviceWorker' in navigator)) {
      return;
    }

    const registration = await navigator.serviceWorker.getRegistration('/notification-sw.js');
    if (!registration) {
      await api.delete('/api/user/settings/notifications/push/subscription', { data: {} });
      return;
    }

    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      const endpoint = subscription.endpoint;
      await subscription.unsubscribe();
      await api.delete('/api/user/settings/notifications/push/subscription', {
        data: { endpoint }
      });
    } else {
      await api.delete('/api/user/settings/notifications/push/subscription', { data: {} });
    }
  };

  const handleToggle = async (key) => {
    if (key === 'notifications') {
      const willEnable = !settings.notifications;
    
      if (!willEnable) {
        try {
          await unregisterPushSubscription();
        } catch (error) {
          console.warn('Push unsubscribe cleanup failed:', error);
        }
        await persistNotificationSettings({ notifications: false }, 'Push notifications disabled.');
        return;
      }

      if (!('Notification' in window)) {
        await persistNotificationSettings(
          { notifications: false, pushPermission: 'unsupported' },
          'This browser does not support push notifications.'
        );
        return;
      }

      let permission = Notification.permission;
      if (permission !== 'granted') {
        permission = await Notification.requestPermission();
      }

      if (permission !== 'granted') {
        await persistNotificationSettings(
          { notifications: false, pushPermission: permission || 'default' },
          'Push notifications are blocked. Enable browser permission to use them.'
        );
        return;
      }

      await registerPushSubscription();

      await persistNotificationSettings(
        { notifications: true, pushPermission: permission },
        'Push notifications enabled successfully.'
      );
      try {
        new Notification('ITDS Notifications Enabled', {
          body: 'You will now receive browser notifications from this app in this browser.'
        });
      } catch (error) {
        console.warn('Unable to display test browser notification:', error);
      }
      return;
    }

    if (key === 'emailAlerts') {
      await persistNotificationSettings(
        { emailAlerts: !settings.emailAlerts },
        !settings.emailAlerts ? 'Email alerts enabled.' : 'Email alerts disabled.'
      );
      return;
    }

    if (key === 'anomalyEmailAlerts') {
      // Admin-only toggle for anomaly alerts
      await persistNotificationSettings(
        { anomalyEmailAlerts: !settings.anomalyEmailAlerts },
        !settings.anomalyEmailAlerts ? 'Anomaly email alerts enabled.' : 'Anomaly email alerts disabled.'
      );
      return;
    }

    const newSettings = { ...settings, [key]: !settings[key] };
    setSettings(newSettings);
    localStorage.setItem('appSettings', JSON.stringify(newSettings));

    if (key === 'darkMode') {
      applyThemeMode(newSettings.darkMode ? 'dark' : 'light');
    }
    
    notifySuccess('Settings updated locally.');
  };

  const handleSendTestEmail = async () => {
    setSendingTestEmail(true);
    try {
      const response = await api.post('/api/user/settings/notifications/test-email', {});
      notifySuccess(response.data?.message || 'Test email sent successfully.');
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to send test email.');
    } finally {
      setSendingTestEmail(false);
    }
  };

  const handleSendTestPush = async () => {
    setSendingTestPush(true);
    try {
      const response = await api.post('/api/user/settings/notifications/test-push', {});
      notifySuccess(response.data?.message || 'Test push sent successfully.');
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to send test push.');
    } finally {
      setSendingTestPush(false);
    }
  };

  const handleSendSystemAlert = async (e) => {
    e.preventDefault();
    setSendingSystemAlert(true);
    try {
      const response = await api.post('/api/admin/notifications/system-status', systemAlert);
      const emailSent = response.data?.email?.sent ?? 0;
      const pushSent = response.data?.push?.sent ?? 0;
      notifySuccess(`System alert sent. Email: ${emailSent}, Push: ${pushSent}`);
      setSystemAlert((prev) => ({ ...prev, message: '' }));
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to dispatch system alert.');
    } finally {
      setSendingSystemAlert(false);
    }
  };

  const validateReportSchedule = (sched) => {
    // If enabling, require at least one recipient email
    if (sched.enabled) {
      const recipients = (sched.recipients || '').trim();
      if (!recipients) return { ok: false, message: 'Please provide at least one recipient email before enabling scheduled reports.' };
      const emails = recipients.split(',').map(e => e.trim()).filter(Boolean);
      const emailRe = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
      for (const e of emails) {
        if (!emailRe.test(e)) return { ok: false, message: `Invalid recipient email: ${e}` };
      }
    }
    // delivery_time basic format
    if (sched.deliveryTime && !/^\d{2}:\d{2}$/.test(sched.deliveryTime)) return { ok: false, message: 'Delivery time must be in HH:MM format.' };
    // deliveryDate basic format if present
    if (sched.deliveryDate && !/^\d{4}-\d{2}-\d{2}$/.test(sched.deliveryDate)) return { ok: false, message: 'Delivery date must be in YYYY-MM-DD format.' };
    return { ok: true };
  };

  const toggleReportScheduleEnabled = () => {
    const next = { ...reportSchedule, enabled: !reportSchedule.enabled };
    setReportSchedule(next);
    localStorage.setItem('reportScheduleSettings', JSON.stringify(next));
    notifySuccess(next.enabled ? 'Scheduled reports enabled.' : 'Scheduled reports disabled.');
  };

  const saveReportSchedule = async (nextSchedule = reportSchedule) => {
    const validation = validateReportSchedule(nextSchedule);
    if (!validation.ok) {
      notifyError(validation.message);
      return;
    }
    setSavingReportSchedule(true);
    const payload = {
      enabled: Boolean(nextSchedule.enabled),
      cadence: nextSchedule.cadence || 'weekly',
      delivery_date: nextSchedule.deliveryDate || '',
      delivery_time: nextSchedule.deliveryTime || '08:00',
      recipient_emails: nextSchedule.recipients || '',
      filters_json: JSON.stringify({
        theme: nextSchedule.theme || '',
        sentiment: nextSchedule.sentiment || 'all'
      })
    };

    try {
      await api.put('/api/user/settings/report-schedules', payload);
      setReportSchedule(createEmptyReportSchedule());
      localStorage.removeItem('reportScheduleSettings');
      notifySuccess('Report schedule saved.');
      // Let other parts of the app know schedule changed (nav badge)
      try { window.dispatchEvent(new Event('report-schedule-updated')); } catch (e) { }
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to save report schedule.');
    }
    finally {
      setSavingReportSchedule(false);
    }
  };

// Handle both lastDeliveryStatus and delivery_date for backward compatibility
  // Also check lastDeliveryAt for more accurate status determination
  const rawStatus = reportSchedule.lastDeliveryStatus
  const rawDeliveryDate = reportSchedule.delivery_date
  const rawDeliveryAt = reportSchedule.lastDeliveryAt
  const hasAttemptedDelivery = rawDeliveryAt || rawDeliveryDate || rawStatus
  const reportDeliveryState = String(rawStatus || rawDeliveryDate || '').toLowerCase()
  
  let reportDeliveryLabel
  if (rawStatus === 'sent' || reportDeliveryState === 'sent') {
    reportDeliveryLabel = 'Last delivery: Sent'
  } else if (rawStatus === 'failed' || reportDeliveryState === 'failed') {
    reportDeliveryLabel = 'Last delivery: Failed'
  } else if (hasAttemptedDelivery) {
    // Show the actual date if we've attempted delivery
    const deliveryTs = rawDeliveryAt || rawDeliveryDate
    if (deliveryTs) {
      try {
        const dateStr = new Date(deliveryTs).toLocaleString()
        reportDeliveryLabel = `Last delivery: ${dateStr}`
      } catch {
        reportDeliveryLabel = 'Last delivery: Completed'
      }
    } else {
      reportDeliveryLabel = 'Last delivery: Completed'
    }
  } else {
    reportDeliveryLabel = 'Last delivery: Pending'
  }

  const handleSelectChange = (key, value) => {
    const newSettings = { ...settings, [key]: value };
    setSettings(newSettings);
    localStorage.setItem('appSettings', JSON.stringify(newSettings));
    if (key === 'language') {
      changeLanguage(value);
    }
    notifySuccess('Settings updated successfully.');
  };

  const testEvaluation = async () => {
    setLoading(true);
    try {
      const response = await api.post('/api/ai/analyze-speech', {
        text: 'Model evaluation test. The team completed all milestones and delivered strong outcomes this quarter.'
      });
      const confidence = Number(response.data?.confidence || 0);
      const sentiment = String(response.data?.sentiment || 'NEUTRAL').toUpperCase();
      notifySuccess(`Evaluation completed successfully. ${sentiment} (${Math.round(confidence * 100)}%).`);
    } catch (error) {
      notifyError(error.response?.data?.details || error.response?.data?.error || 'Evaluation failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const testAISummarize = async () => {
    setLoading(true);
    try {
      const response = await api.post('/api/ai/analyze-speech', {
        text: 'This is a test meeting minutes document. We discussed curriculum development, student internships, and budget planning. The meeting was successful and we achieved our goals.'
      });
      const summary = String(response.data?.summary || 'Summary generated successfully.');
      notifySuccess('Summary generated: ' + summary.substring(0, 70) + (summary.length > 70 ? '...' : ''));
    } catch (error) {
      notifyError(error.response?.data?.details || error.response?.data?.error || 'Summarization failed. Please retry.');
    } finally {
      setLoading(false);
    }
  };

  const testSentiment = async () => {
    setLoading(true);
    try {
      const response = await api.post('/api/ai/analyze-speech', {
        text: 'We had a great meeting with positive outcomes and excellent progress on all initiatives.'
      });
      notifySuccess('Sentiment analysis complete: ' + String(response.data?.sentiment || 'NEUTRAL').toUpperCase());
    } catch (error) {
      notifyError(error.response?.data?.details || error.response?.data?.error || 'Sentiment analysis failed. Please retry.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-content">
      <div className="dashboard">
        <div className="dashboard-header">
          <h1 className="dashboard-title">{t('navSettings')}</h1>
          <p className="dashboard-subtitle">{t('managePreferences')}</p>
        </div>

<div className="settings-container">
          {/* Appearance Section */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="5"></circle>
                  <line x1="12" y1="1" x2="12" y2="3"></line>
                  <line x1="12" y1="21" x2="12" y2="23"></line>
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                  <line x1="1" y1="12" x2="3" y2="12"></line>
                  <line x1="21" y1="12" x2="23" y2="12"></line>
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                </svg>
                {t('appearance')}
              </h3>
            </div>
            <div className="card-body">
              <div className="form-group">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="form-label">{t('darkMode')}</label>
                    <p className="text-sm text-secondary">{t('switchTheme')}</p>
                  </div>
                  <button 
                    className={`btn ${settings.darkMode ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => handleToggle('darkMode')}
                  >
                    {settings.darkMode ? 'On' : 'Off'}
                  </button>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">{t('language')}</label>
                <select 
                  className="form-select"
                  value={settings.language}
                  onChange={(e) => handleSelectChange('language', e.target.value)}
                >
                  <option value="en">English</option>
                  <option value="es">Español</option>
                  <option value="fr">Français</option>
                </select>
              </div>
            </div>
          </div>

          {/* Notifications Section */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                  <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                </svg>
                {t('notifications')}
              </h3>
            </div>
            <div className="card-body">
              <div className="form-group">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="form-label">{t('pushNotifications')}</label>
                    <p className="text-sm text-secondary">{t('receiveNotifications')}</p>
                  </div>
                  <button 
                    className={`btn ${settings.notifications ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => handleToggle('notifications')}
                    disabled={savingSettings}
                  >
                    {settings.notifications ? 'On' : 'Off'}
                  </button>
                </div>
                <p className="text-xs text-secondary mt-1">
                  Browser permission: {settings.pushPermission}
                </p>
                {isSuperAdmin && (
                  <div className="mt-2">
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={handleSendTestPush}
                      disabled={sendingTestPush || !settings.notifications}
                    >
                      {sendingTestPush ? 'Sending test push...' : 'Send test push'}
                    </button>
                  </div>
                )}
              </div>

              <div className="form-group">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="form-label">{t('emailAlerts')}</label>
                    <p className="text-sm text-secondary">{t('receiveEmail')}</p>
                  </div>
                  <button 
                    className={`btn ${settings.emailAlerts ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => handleToggle('emailAlerts')}
                    disabled={savingSettings}
                  >
                    {settings.emailAlerts ? 'On' : 'Off'}
                  </button>
                </div>
                {canAccessAdminSettings && (
                  <div className="mt-2">
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={handleSendTestEmail}
                      disabled={sendingTestEmail || !settings.emailAlerts}
                    >
                      {sendingTestEmail ? 'Sending test email...' : 'Send test email'}
                    </button>
                  </div>
                )}
              </div>

              {canAccessAdminSettings && (
                <div className="form-group">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="form-label">Anomaly Email Alerts</label>
                      <p className="text-sm text-secondary">Enable critical anomaly emails to admins</p>
                    </div>
                    <button 
                      className={`btn ${settings.anomalyEmailAlerts ? 'btn-primary' : 'btn-outline'}`}
                      onClick={() => handleToggle('anomalyEmailAlerts')}
                      disabled={savingSettings}
                    >
                      {settings.anomalyEmailAlerts ? 'On' : 'Off'}
                    </button>
                  </div>
                </div>
              )}

              {isSuperAdmin && (
                <div className="form-group mt-4 system-alert-section">
                  <button
                    type="button"
                    className={`system-alert-toggle ${isSystemAlertOpen ? 'is-open' : ''}`}
                    onClick={() => setIsSystemAlertOpen((prev) => !prev)}
                    aria-expanded={isSystemAlertOpen}
                  >
                    <span className="system-alert-toggle-label">System Status Alert</span>
                    <span className="system-alert-toggle-meta">Super Admin</span>
                  </button>

                  <div
                    className={`system-alert-panel ${isSystemAlertOpen ? 'is-open' : ''}`}
                    aria-hidden={!isSystemAlertOpen}
                  >
                    <p className="text-sm text-secondary mb-3">Send a live operational alert to users who opted in.</p>
                    <form onSubmit={handleSendSystemAlert}>
                      <input
                        type="text"
                        className="form-input mb-2 system-alert-input"
                        placeholder="Alert title"
                        value={systemAlert.title}
                        onChange={(e) => setSystemAlert((prev) => ({ ...prev, title: e.target.value }))}
                        required
                      />
                      <textarea
                        className="form-input mb-2 system-alert-input system-alert-textarea"
                        placeholder="Alert message"
                        value={systemAlert.message}
                        onChange={(e) => setSystemAlert((prev) => ({ ...prev, message: e.target.value }))}
                        rows={3}
                        required
                      />
                      <select
                        className="form-select mb-3 system-alert-input"
                        value={systemAlert.severity}
                        onChange={(e) => setSystemAlert((prev) => ({ ...prev, severity: e.target.value }))}
                      >
                        <option value="info">Info</option>
                        <option value="warning">Warning</option>
                        <option value="critical">Critical</option>
                      </select>
                      <button className="btn btn-primary btn-sm" type="submit" disabled={sendingSystemAlert}>
                        {sendingSystemAlert ? 'Sending alert...' : 'Send system alert'}
                      </button>
                    </form>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Notifications Section remains, Profile Image card removed - handled by dropdown modal */}

          {canManageReportDelivery && (
            <div className="card" id="report-schedule-settings">
              <div className="card-header">
                <h3 className="card-title">Data & Reporting</h3>
              </div>
              <div className="card-body">
                <div className="grid grid-2 gap-3">
                  <div className="form-group">
                    <label className="form-label">Scheduled reports</label>
                    <p className="text-sm text-secondary">Auto-generate a report snapshot and email it on a schedule.</p>
                    <p className="text-sm mt-1" style={{ color: reportDeliveryState === 'sent' ? '#1f7a4f' : reportDeliveryState === 'failed' ? '#b42318' : '#6b7280' }}>
                      {reportDeliveryLabel}
                      {reportSchedule.lastDeliveryAt ? ` on ${new Date(reportSchedule.lastDeliveryAt).toLocaleString()}` : ''}
                    </p>
                    {reportSchedule.lastDeliveryError ? (
                      <p className="text-xs text-secondary mt-1">Error: {reportSchedule.lastDeliveryError}</p>
                    ) : null}
                    <div className="button-group mt-2">
                      <button type="button" className={`btn btn-sm ${reportSchedule.enabled ? 'btn-success' : 'btn-outline'}`} onClick={toggleReportScheduleEnabled} disabled={savingReportSchedule}>
                        {reportSchedule.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => saveReportSchedule(reportSchedule)} disabled={savingReportSchedule}>{savingReportSchedule ? 'Saving...' : 'Save'}</button>
                    </div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Cadence</label>
                    <select className="form-select" value={reportSchedule.cadence} onChange={(e) => setReportSchedule((prev) => ({ ...prev, cadence: e.target.value }))}>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Delivery time</label>
                    <input className="form-input" type="time" value={reportSchedule.deliveryTime} onChange={(e) => setReportSchedule((prev) => ({ ...prev, deliveryTime: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Delivery date</label>
                    <input className="form-input" type="date" value={reportSchedule.deliveryDate} onChange={(e) => setReportSchedule((prev) => ({ ...prev, deliveryDate: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Recipient emails</label>
                    <input className="form-input" value={reportSchedule.recipients} onChange={(e) => setReportSchedule((prev) => ({ ...prev, recipients: e.target.value }))} placeholder="ops@example.com, manager@example.com" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Default theme filter</label>
                    <select className="form-select" value={reportSchedule.theme} onChange={(e) => setReportSchedule((prev) => ({ ...prev, theme: e.target.value }))}>
                      <option value="">All themes</option>
                      {themes.map((th) => (
                        <option key={th} value={th}>{th}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Default sentiment filter</label>
                    <select className="form-select" value={reportSchedule.sentiment} onChange={(e) => setReportSchedule((prev) => ({ ...prev, sentiment: e.target.value }))}>
                      <option value="all">All</option>
                      <option value="positive">Positive</option>
                      <option value="neutral">Neutral</option>
                      <option value="negative">Negative</option>
                    </select>
                  </div>
                </div>
                <div className="mt-3 button-group">
                  <button className="btn btn-outline btn-sm" onClick={() => window.location.assign('/reports')}>
                    Open Reports
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => window.location.assign('/reports/schedules')}>
                    View Schedule Table
                  </button>
                  <button className="btn btn-primary btn-sm" onClick={() => window.location.assign('/upload')}>
                    Open Import
                  </button>
                  <button className="btn btn-success btn-sm" onClick={() => window.location.assign('/charts')}>
                    Open Comparison
                  </button>
                </div>
                {isSuperAdmin && adminSchedules.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm text-secondary mb-2">Admin schedule archive</p>
                    <div style={{ maxHeight: 320, overflow: 'auto' }}>
                      <table className="table">
                        <thead>
                          <tr>
                            <th>ID</th>
                            <th>User</th>
                            <th>Cadence</th>
                            <th>Time</th>
                            <th>Enabled</th>
                            <th>Deleted</th>
                            <th>Last Delivery</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {adminSchedules.map((s) => (
                            <tr key={s.schedule_id}>
                              <td>{s.schedule_id}</td>
                              <td>{s.username || s.email || s.user_id}</td>
                              <td>{s.cadence}</td>
                              <td>{s.delivery_time}</td>
                              <td>{s.enabled ? 'Yes' : 'No'}</td>
                              <td>{s.is_deleted ? `Yes${s.deleted_at ? ' ' + new Date(s.deleted_at).toLocaleString() : ''}` : 'No'}</td>
                              <td>{s.last_delivery_status ? `${s.last_delivery_status}${s.last_delivery_at ? ' on ' + new Date(s.last_delivery_at).toLocaleString() : ''}` : '-'}</td>
                              <td>
                                {s.is_deleted ? (
                                  <button className="btn btn-sm btn-success" onClick={async () => {
                                    try {
                                      await api.post(`/api/admin/report-schedules/${s.schedule_id}/restore`);
                                      notifySuccess('Schedule restored');
                                      const resp = await api.get('/api/admin/report-schedules?include_deleted=true&limit=500');
                                      setAdminSchedules(resp.data?.schedules || []);
                                    } catch (err) {
                                      notifyError(err.response?.data?.error || 'Failed to restore');
                                    }
                                  }}>Restore</button>
                                ) : (<span style={{ color: '#6b7280' }}>—</span>)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {canAccessAdminSettings && (
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                </svg>
                Admin Roles Settings
              </h3>
            </div>
            <div className="card-body">
              <p className="text-sm text-secondary mb-4">System tests for admin and super admin roles.</p>
              
              <div className="flex flex-col gap-3">
<button 
                  className="btn btn-primary"
                  onClick={testEvaluation}
                  disabled={loading}
                >
                  {t('testModelEvaluation')}
                </button>
                
                <button 
                  className="btn btn-secondary"
                  onClick={testAISummarize}
                  disabled={loading}
                >
                  {t('testAISummarization')}
                </button>
                
                <button 
                  className="btn btn-outline"
                  onClick={testSentiment}
                  disabled={loading}
                >
                  {t('testSentimentAnalysis')}
                </button>
              </div>
            </div>
          </div>

          )}

          {/* About Section */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="16" x2="12" y2="12"></line>
                  <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
                {t('about')}
              </h3>
            </div>
            <div className="card-body">
              <div className="mb-4">
                <p className="font-medium">ITDS Board Minutes Analysis System</p>
                <p className="text-sm text-secondary">{t('version')} 1.0.0</p>
              </div>
              
              <div className="mb-4">
                <p className="text-sm">
                  <strong>{t('user')}:</strong> {user?.username || 'Guest'}
                </p>
                <p className="text-sm">
                  <strong>Email:</strong> {user?.email || 'N/A'}
                </p>
                <p className="text-sm">
                  <strong>{t('role')}:</strong> {user?.role || 'N/A'}
                </p>
                {user?.profile_image && (
                  <p className="text-sm mt-1">
                    <strong>Profile:</strong> <span className="text-primary">Uploaded</span>
                  </p>
                )}
              </div>
              
              <div className="tag tag-primary">
                Backend Integrated
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;

