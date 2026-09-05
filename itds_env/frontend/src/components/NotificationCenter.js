import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Archive, Check, RotateCcw, Trash2 } from 'lucide-react';
import { notificationsAPI } from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { useConfirm } from './ConfirmProvider';

const formatTimestamp = (value, fallback) => {
  if (!value) return fallback;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
};

const statusClass = (status) => {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'sent' || normalized === 'delivered') return 'tag tag-success';
  if (normalized === 'failed') return 'tag tag-warning';
  return 'tag tag-neutral';
};

const isReadNotification = (item) => Boolean(item?.is_read);
const isDeletedNotification = (item) => Boolean(item?.is_deleted);
const isArchivedNotification = (item) => Boolean(item?.is_archived);

const channelClass = (channel) => {
  const normalized = String(channel || '').toLowerCase();
  if (normalized === 'push') return 'tag tag-primary';
  if (normalized === 'email') return 'tag tag-success';
  return 'tag tag-neutral';
};

const toCount = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const normalizeCounts = (counts = {}) => {
  const total = toCount(counts.total, 0);
  const unread = toCount(counts.unread, 0);
  const read = toCount(counts.read, Math.max(total - unread, 0));
  return {
    total,
    unread,
    read,
    received: toCount(counts.received, 0),
    sent: toCount(counts.sent, 0),
    email: toCount(counts.email, 0),
    push: toCount(counts.push, 0),
    archived: toCount(counts.archived, 0),
    deleted: toCount(counts.deleted, 0),
  };
};

const NotificationCenter = () => {
  const { t } = useLanguage();
  const { isSuperAdmin } = useAuth();
  const confirm = useConfirm();
  const canUseGlobalScope = isSuperAdmin();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [clearingAll, setClearingAll] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [summary, setSummary] = useState({ total: 0, unread: 0, read: 0, received: 0, sent: 0, email: 0, push: 0, archived: 0, deleted: 0 });
  const [tab, setTab] = useState('all');
  const [channel, setChannel] = useState('all');
  const [scope, setScope] = useState(canUseGlobalScope ? 'all' : 'mine');
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);

  useEffect(() => {
    if (!canUseGlobalScope && scope !== 'mine') {
      setScope('mine');
    }
  }, [canUseGlobalScope, scope]);

  const loadNotifications = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      const response = await notificationsAPI.getNotifications({ tab, channel, scope, limit: 50, _ts: Date.now() });
      setNotifications(response.data?.items || []);
      setSummary((prev) => normalizeCounts(response.data?.counts || prev));
      setLastRefreshedAt(new Date());
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsFailedLoad'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tab, channel, scope, t]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  const markRead = async (notificationId) => {
    try {
      await notificationsAPI.markAsRead(notificationId);
      notifySuccess(t('notificationsMarkedRead'));
      await loadNotifications({ silent: true });
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsMarkReadFailed'));
    }
  };

  const markAllRead = async () => {
    try {
      await notificationsAPI.markAllAsRead({ scope });
      notifySuccess(t('notificationsMarkedAllRead'));
      await loadNotifications({ silent: true });
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsMarkAllReadFailed'));
    }
  };

  const clearAllNotifications = async () => {
    const result = await confirm({
      title: t('notificationsClearAll'),
      message: t('notificationsClearAllConfirm'),
      actions: [{ label: t('notificationsClearAll'), value: 'clear', variant: 'danger' }],
      cancelLabel: t('cancel'),
    });
    if (result.action !== 'clear') return;

    setClearingAll(true);
    try {
      await notificationsAPI.clearAll({ scope, tab, channel });
      notifySuccess(t('notificationsClearedAll'));
      await loadNotifications({ silent: true });
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsClearAllFailed'));
    } finally {
      setClearingAll(false);
    }
  };

  const deleteNotification = async (notificationId) => {
    try {
      await notificationsAPI.deleteNotification(notificationId);
      notifySuccess(t('notificationsDeleted'));
      await loadNotifications({ silent: true });
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsDeleteFailed'));
    }
  };

  const archiveNotification = async (notificationId) => {
    try {
      await notificationsAPI.archiveNotification(notificationId);
      notifySuccess(t('notificationsArchived'));
      await loadNotifications({ silent: true });
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsArchiveFailed'));
    }
  };

  const restoreNotification = async (notificationId) => {
    try {
      await notificationsAPI.restoreNotification(notificationId);
      notifySuccess(t('notificationsRestored'));
      await loadNotifications({ silent: true });
    } catch (error) {
      notifyError(error.response?.data?.error || t('notificationsRestoreFailed'));
    }
  };

  const visibleCountLabel = useMemo(() => {
    if (tab === 'sent') return t('notificationsSent');
    if (tab === 'received') return t('notificationsReceived');
    if (tab === 'archived') return t('notificationsArchivedLabel');
    if (tab === 'read') return t('notificationsRead');
    if (tab === 'unread') return t('notificationsUnread');
    if (tab === 'deleted') return t('notificationsDeletedLabel');
    return t('notificationsAll');
  }, [tab, t]);

  const tabLabel = (value) => {
    if (value === 'sent') return t('notificationsSent');
    if (value === 'received') return t('notificationsReceived');
    if (value === 'archived') return t('notificationsArchivedLabel');
    if (value === 'read') return t('notificationsRead');
    if (value === 'unread') return t('notificationsUnread');
    if (value === 'deleted') return t('notificationsDeletedLabel');
    return t('notificationsAll');
  };

  const channelLabel = (value) => {
    if (value === 'email') return t('notificationsChannelEmail');
    if (value === 'push') return t('notificationsChannelPush');
    return t('notificationsAll');
  };

  const channelBadgeLabel = (value) => {
    const normalized = String(value || '').toLowerCase();
    if (normalized === 'email') return t('notificationsChannelEmail').toUpperCase();
    if (normalized === 'push') return t('notificationsChannelPush').toUpperCase();
    return t('notificationsChannelMail').toUpperCase();
  };

  const statusBadgeLabel = (value) => {
    const normalized = String(value || '').toLowerCase();
    if (normalized === 'sent') return t('notificationsStatusSent').toUpperCase();
    if (normalized === 'delivered') return t('notificationsStatusDelivered').toUpperCase();
    if (normalized === 'failed') return t('notificationsStatusFailed').toUpperCase();
    return t('notificationsStatusUnknown').toUpperCase();
  };

  return (
    <div className="page-content">
      <div className="dashboard notification-center-shell">
        <div className="dashboard-header notification-center-header flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="dashboard-title">{t('navNotifications')}</h1>
            <p className="dashboard-subtitle">{t('notificationsSubtitle')}</p>
          </div>
          <div className="flex gap-2 flex-wrap items-center">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-xs text-muted whitespace-nowrap">
                {t('alLastUpdated')}: {lastRefreshedAt ? formatTimestamp(lastRefreshedAt, t('navLastUpdatedJustNow')) : t('navLastUpdatedJustNow')}
              </span>
              {canUseGlobalScope && (
                <span className="text-xs text-muted whitespace-nowrap">
                  {t('notificationsScopeLabel')}: {scope === 'all' ? t('notificationsScopeAllUsers') : t('notificationsScopeMyAccount')}
                </span>
              )}
              <button className="btn btn-outline btn-sm" onClick={() => loadNotifications({ silent: true })} disabled={refreshing}>
                {refreshing ? t('notificationsRefreshing') : t('uploadRefresh')}
              </button>
            </div>
            <button className="btn btn-primary btn-sm" onClick={markAllRead} disabled={!summary.unread}>
              {t('navMarkAllRead')}
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={clearAllNotifications}
              disabled={clearingAll || notifications.length === 0 || tab === 'deleted'}
            >
              {clearingAll ? t('notificationsClearingAll') : t('notificationsClearAll')}
            </button>
          </div>
        </div>

        <div className="notification-center-stats grid gap-4 md:grid-cols-2 xl:grid-cols-4 mb-4">
          <div className="notification-stat-card"><div className="notification-stat-label">{t('notificationsUnread')}</div><div className="notification-stat-value">{summary.unread}</div></div>
          <div className="notification-stat-card"><div className="notification-stat-label">{t('notificationsRead')}</div><div className="notification-stat-value">{summary.read}</div></div>
          <div className="notification-stat-card"><div className="notification-stat-label">{t('notificationsArchivedLabel')}</div><div className="notification-stat-value">{summary.archived}</div></div>
          <div className="notification-stat-card"><div className="notification-stat-label">{t('notificationsReceived')}</div><div className="notification-stat-value">{summary.received}</div></div>
          <div className="notification-stat-card"><div className="notification-stat-label">{t('notificationsDeletedLabel')}</div><div className="notification-stat-value">{summary.deleted}</div></div>
          <div className="notification-stat-card"><div className="notification-stat-label">{t('notificationsEmailPush')}</div><div className="notification-stat-value">{summary.email} / {summary.push}</div></div>
        </div>

        <div className="card notification-center-toolbar mb-4">
          <div className="card-body flex flex-wrap gap-2 items-center justify-between">
            <div className="flex gap-2 flex-wrap">
              {['all', 'sent', 'received', 'archived', 'read', 'unread', 'deleted'].map((value) => (
                <button
                  key={value}
                  className={`btn btn-sm notification-tab ${value === 'archived' ? 'notification-tab-archived' : ''} ${value === 'deleted' ? 'notification-tab-deleted' : ''} ${tab === value ? 'btn-primary' : 'btn-outline'}`}
                  onClick={() => setTab(value)}
                >
                  {tabLabel(value)}
                </button>
              ))}
            </div>
            <div className="flex gap-2 flex-wrap items-center">
              <span className="text-sm text-secondary">{t('notificationsChannelLabel')}</span>
              {['all', 'email', 'push'].map((value) => (
                <button
                  key={value}
                  className={`btn btn-sm ${channel === value ? 'btn-secondary' : 'btn-outline'}`}
                  onClick={() => setChannel(value)}
                >
                  {channelLabel(value)}
                </button>
              ))}
              {canUseGlobalScope && (
                <>
                  <span className="text-sm text-secondary">{t('notificationsScopeLabel')}</span>
                  <button
                    className={`btn btn-sm ${scope === 'all' ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setScope('all')}
                  >
                    {t('notificationsScopeAllUsers')}
                  </button>
                  <button
                    className={`btn btn-sm ${scope === 'mine' ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setScope('mine')}
                  >
                    {t('notificationsScopeMyAccount')}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="card notification-center-list-card">
          <div className="card-header notification-center-list-header">
            <h3 className="card-title">{t('notificationsCountTitle', { label: visibleCountLabel })}</h3>
          </div>
          <div className="card-body notification-center-list-body">
            {loading ? (
              <div className="loading min-h-[240px]"><div className="spinner"></div></div>
            ) : notifications.length === 0 ? (
              <div className="text-center py-10 text-muted">{t('notificationsNoItems')}</div>
            ) : (
              <div className="notification-center-list flex flex-col gap-3">
                {notifications.map((item) => (
                  <div key={item.notification_id} className={`notification-item ${isReadNotification(item) ? 'read' : 'unread'} ${isArchivedNotification(item) ? 'archived' : ''} ${isDeletedNotification(item) ? 'deleted' : ''}`}>
                    <div className="notification-item-content">
                      <div className="space-y-2 notification-item-main">
                        <div className="flex flex-wrap gap-2 items-center">
                          <span className={channelClass(item.channel)}>{channelBadgeLabel(item.channel)}</span>
                          <span className={statusClass(item.status)}>{statusBadgeLabel(item.status)}</span>
                          {isReadNotification(item) && <span className="tag tag-success">{t('notificationsRead')}</span>}
                          {isArchivedNotification(item) && <span className="tag tag-neutral">{t('notificationsArchivedLabel')}</span>}
                          {isDeletedNotification(item) && <span className="tag tag-warning">{t('notificationsDeletedLabel')}</span>}
                          {!isReadNotification(item) && <span className="tag tag-warning">{t('notificationsUnreadTag')}</span>}
                        </div>
                        <h4 className="font-semibold text-lg">{item.title}</h4>
                        {item.body && (
                          <p className="text-sm text-secondary notification-message-body notification-tooltip-target" data-tooltip={item.body} aria-label={item.body}>
                            {item.body}
                          </p>
                        )}
                        <div className="text-xs text-muted flex flex-wrap gap-3">
                          <span>{formatTimestamp(item.created_at, t('reportsNA'))}</span>
                          {item.recipient_email && <span>{item.recipient_email}</span>}
                          {item.actor_username && <span>{t('notificationsByActor', { actor: item.actor_username })}</span>}
                          {item.error_message && <span className="notification-error-inline notification-tooltip-target" data-tooltip={item.error_message} aria-label={item.error_message}>{item.error_message}</span>}
                        </div>
                      </div>
                      <div className="notification-item-actions">
                        {!isReadNotification(item) && !isDeletedNotification(item) && (
                          <button className="btn btn-outline btn-sm notification-action-btn" onClick={() => markRead(item.notification_id)} title={t('notificationsMarkRead')} aria-label={t('notificationsMarkRead')}>
                            <span className="notification-action-icon" aria-hidden="true"><Check size={16} /></span>
                            <span className="notification-action-text">{t('notificationsMarkRead')}</span>
                          </button>
                        )}
                        {!isDeletedNotification(item) && !isArchivedNotification(item) && (
                          <button className="btn btn-secondary btn-sm notification-action-btn" onClick={() => archiveNotification(item.notification_id)} title={t('notificationsArchive')} aria-label={t('notificationsArchive')}>
                            <span className="notification-action-icon" aria-hidden="true"><Archive size={16} /></span>
                            <span className="notification-action-text">{t('notificationsArchive')}</span>
                          </button>
                        )}
                        {(isDeletedNotification(item) || isArchivedNotification(item)) && (
                          <button className="btn btn-outline btn-sm notification-action-btn" onClick={() => restoreNotification(item.notification_id)} title={t('notificationsRestore')} aria-label={t('notificationsRestore')}>
                            <span className="notification-action-icon" aria-hidden="true"><RotateCcw size={16} /></span>
                            <span className="notification-action-text">{t('notificationsRestore')}</span>
                          </button>
                        )}
                        {!isDeletedNotification(item) && (
                          <button className="btn btn-danger btn-sm notification-action-btn" onClick={() => deleteNotification(item.notification_id)} title={t('notificationsDelete')} aria-label={t('notificationsDelete')}>
                            <span className="notification-action-icon" aria-hidden="true"><Trash2 size={16} /></span>
                            <span className="notification-action-text">{t('notificationsDelete')}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default NotificationCenter;
