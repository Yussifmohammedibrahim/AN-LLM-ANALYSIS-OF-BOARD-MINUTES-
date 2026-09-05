import React, { useEffect, useState, useRef } from 'react';
import api from '../api/api';
import { aiAPI } from '../api/api';
import { useNavigate } from 'react-router-dom';
import { Trash2, Undo2, X } from 'lucide-react';
import { toast } from 'react-toastify';
import { notifyError, notifySuccess } from '../utils/notify';
import { useAuth } from '../context/AuthContext';
import { useConfirm } from './ConfirmProvider';

const ScheduledReports = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const confirm = useConfirm();
  const [loading, setLoading] = useState(true);
  const [schedule, setSchedule] = useState(null);
  const [history, setHistory] = useState(null);
  const [aggregatedSchedules, setAggregatedSchedules] = useState(null);
  const [error, setError] = useState(null);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
const [themes, setThemes] = useState([]);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [clearingAll, setClearingAll] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const autoRefreshRef = useRef(null);
  const [scope, setScope] = useState('all');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [, setIsRefreshingMy] = useState(false);

  // Auto-refresh handler (admin and super_admin). Toggle using UI control.
  useEffect(() => {
    if (!autoRefresh) {
      if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
        autoRefreshRef.current = null;
      }
      return;
    }
    const refreshFn = user?.role === 'super_admin' ? refreshAggregatedSchedules : refreshCurrentSchedule;
    // refresh every 60s
    autoRefreshRef.current = setInterval(async () => {
      try {
        await refreshFn();
      } catch (e) { /* ignore */ }
    }, 60000);
    // do an immediate refresh when enabling
    (async () => { try { await refreshFn(); } catch {} })();
    return () => {
      if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
        autoRefreshRef.current = null;
      }
    };
  }, [autoRefresh, user?.role]);

  useEffect(() => {
    if (user && !['editor', 'admin', 'super_admin'].includes(user.role)) {
      notifyError('You do not have permission to access Schedule Delivery.');
      navigate('/');
    }
  }, [user, navigate]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        // Load aggregated schedules for SuperAdmin only
        if (user?.role === 'super_admin') {
          try {
            const aggResp = await api.get('/api/admin/aggregated-report-schedules');
            if (mounted) setAggregatedSchedules(aggResp.data);
          } catch (aggErr) {
            console.warn('Failed to load aggregated schedules:', aggErr?.message || aggErr);
          }
        }

        // Try to load history first (backend may not have this endpoint)
        try {
          const histResp = await api.get('/api/user/settings/report-schedules/history');
          if (mounted) setHistory(histResp.data?.schedules || []);
        } catch (histErr) {
          // Endpoint may not exist yet — ignore
          if (histErr.response && histErr.response.status === 404) {
            // no-op
          } else {
            console.debug('No history endpoint or failed to load history', histErr?.message || histErr);
          }
        }

        const resp = await api.get('/api/user/settings/report-schedules');
        if (!mounted) return;
        setSchedule(resp.data?.schedule || null);
      } catch (err) {
        console.warn('Failed to load scheduled reports:', err);
        if (mounted) setError('Unable to load schedule.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();

    // load available themes for modal dropdown
    const loadThemes = async () => {
      try {
        const resp = await aiAPI.getDynamicThemes();
        const extracted = resp.data?.themes || [];
        const unique = Array.isArray(extracted) ? Array.from(new Set(extracted.map(t => (typeof t === 'string' ? t : (t.name || ''))).filter(Boolean))) : [];
        if (mounted) setThemes(unique);
      } catch (err) {
        console.debug('Unable to load themes for ScheduledReports:', err?.message || err);
      }
    };
    loadThemes();
    return () => { mounted = false; };
  }, [user?.role]);

  const formatTime12Hr = (time24) => {
    if (!time24) return '-';
    const [hours, minutes] = time24.split(':');
    const h = parseInt(hours, 10);
    const m = minutes || '00';
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${h12}:${m} ${ampm}`;
  };

  const isDeliveryDue = (delivery_time, last_delivery_at) => {
    try {
      if (!delivery_time) return false;
      // If last_delivery_at exists and is after delivery_time today, it's not due
      const now = new Date();
      const [h, m] = (delivery_time || '00:00').split(':').map(x => parseInt(x, 10));
      const scheduled = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h || 0, m || 0, 0);
      if (last_delivery_at) {
        const last = new Date(last_delivery_at);
        // If last delivery is today and after scheduled time, then not due
        if (last.toDateString() === scheduled.toDateString() && last >= scheduled) return false;
      }
      return now > scheduled;
    } catch (e) {
      return false;
    }
  };

  const getDisplayDeliveryStatus = (scheduleRow) => {
    const deliveryStatus = scheduleRow.last_delivery_status;
    const normalized = String(deliveryStatus || '').toLowerCase();
    const due = isDeliveryDue(scheduleRow.delivery_time, scheduleRow.last_delivery_at);
    const statusValue = due && (!deliveryStatus || normalized === 'pending') ? 'Due' : (deliveryStatus || 'Pending');
    const statusStyle = {
      padding: '2px 6px',
      borderRadius: 3,
      background: (statusValue === 'sent' || statusValue === 'success') ? '#d4edda' : statusValue === 'failed' ? '#f8d7da' : (statusValue === 'Due' ? '#fff4e5' : '#fff3cd'),
      color: (statusValue === 'sent' || statusValue === 'success') ? '#155724' : statusValue === 'failed' ? '#721c24' : (statusValue === 'Due' ? '#8a6d3b' : '#856404')
    };
    return { statusValue, statusStyle };
  };

  const getLastSendResult = (scheduleRow) => {
    const status = String(scheduleRow?.last_delivery_status || '').toLowerCase();
    if (status === 'failed') {
      return scheduleRow?.last_delivery_error || 'Last send failed.';
    }
    if (status === 'sent' || status === 'success') {
      return scheduleRow?.last_delivery_at
        ? `Delivered at ${new Date(scheduleRow.last_delivery_at).toLocaleString()}`
        : 'Delivered successfully.';
    }
    const due = isDeliveryDue(scheduleRow?.delivery_time, scheduleRow?.last_delivery_at);
    return due ? 'Due for delivery; waiting for dispatcher run.' : 'Waiting for next schedule window.';
  };

  const getAggregatedRowsByScope = () => {
    const all = aggregatedSchedules?.aggregated || [];
    if (scope === 'all') return all;
    const currentUserId = user?.user_id || user?.id;
    const currentUsername = String(user?.username || '').toLowerCase();
    const currentEmail = String(user?.email || '').toLowerCase();
    return all.filter((group) => {
      const groupUserId = group?.user_id;
      const groupUsername = String(group?.username || '').toLowerCase();
      const groupEmail = String(group?.email || '').toLowerCase();
      if (currentUserId && groupUserId && String(currentUserId) === String(groupUserId)) return true;
      if (currentEmail && groupEmail && currentEmail === groupEmail) return true;
      if (currentUsername && groupUsername && currentUsername === groupUsername) return true;
      return false;
    });
  };

  const formatFilters = (filtersJson) => {
    try {
      const filters = typeof filtersJson === 'string' ? JSON.parse(filtersJson) : filtersJson;
      if (!filters || Object.keys(filters).length === 0) return '(all)';
      const parts = [];
      if (filters.theme) parts.push(`Theme: ${filters.theme}`);
      if (filters.sentiment && filters.sentiment !== 'all') parts.push(`Sentiment: ${filters.sentiment}`);
      return parts.length > 0 ? parts.join(', ') : '(all)';
    } catch {
      return '(all)';
    }
  };

  const openEditModal = (s) => {
    const filters = (() => {
      try { return s.filters_json ? (typeof s.filters_json === 'string' ? JSON.parse(s.filters_json) : s.filters_json) : {}; } catch { return {}; }
    })();
    setEditingSchedule({
      enabled: Boolean(s.enabled),
      cadence: s.cadence || 'weekly',
      delivery_date: s.delivery_date || '',
      delivery_time: s.delivery_time || '08:00',
      recipient_emails: s.recipient_emails || '',
      theme: filters.theme || '',
      sentiment: filters.sentiment || 'all'
    });
    setEditModalOpen(true);
  };

  const closeEditModal = () => {
    setEditModalOpen(false);
    setEditingSchedule(null);
  };

  const refreshCurrentSchedule = async () => {
    setIsRefreshingMy(true);
    try {
      const [scheduleResp, histResp] = await Promise.all([
        api.get('/api/user/settings/report-schedules'),
        api.get('/api/user/settings/report-schedules/history')
      ]);
      setSchedule(scheduleResp.data?.schedule || null);
      setHistory(histResp.data?.schedules || []);
      toast.success('Schedule refreshed');
    } catch (err) {
      console.warn('refreshCurrentSchedule failed', err);
    } finally {
      setIsRefreshingMy(false);
    }
  };

  const refreshAggregatedSchedules = async () => {
    setIsRefreshing(true);
    try {
      const aggResp = await api.get('/api/admin/aggregated-report-schedules');
      setAggregatedSchedules(aggResp.data);
      setLastRefresh(new Date().toLocaleString());
      toast.success('Aggregated schedules refreshed');
    } catch (err) {
      notifyError(err.response?.data?.error || 'Failed to refresh aggregated schedules');
    } finally {
      setIsRefreshing(false);
    }
  };

  const saveEdit = async () => {
    if (!editingSchedule.recipient_emails.trim() && editingSchedule.enabled) {
      notifyError('Please enter at least one recipient email');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        enabled: editingSchedule.enabled,
        cadence: editingSchedule.cadence,
        delivery_date: editingSchedule.delivery_date,
        delivery_time: editingSchedule.delivery_time,
        recipient_emails: editingSchedule.recipient_emails,
        filters_json: JSON.stringify({ theme: editingSchedule.theme, sentiment: editingSchedule.sentiment })
      };
      await api.put('/api/user/settings/report-schedules', payload);
      notifySuccess('Schedule updated successfully');
      closeEditModal();
      // Reload
      await refreshCurrentSchedule();
    } catch (err) {
      notifyError(err.response?.data?.error || 'Failed to save schedule');
    } finally {
      setSaving(false);
    }
  };

  const deleteSchedule = async (s) => {
    if (!s || !s.schedule_id) {
      notifyError('Cannot delete this schedule');
      return;
    }
    try {
      await api.delete(`/api/user/settings/report-schedules/${s.schedule_id}`);
      notifySuccess('Schedule deleted');
      await refreshCurrentSchedule();
      toast.info(({ closeToast }) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span>Schedule deleted</span>
          <button
            type="button"
            onClick={async () => {
              try {
                const filters = s.filters_json ? (typeof s.filters_json === 'string' ? JSON.parse(s.filters_json) : s.filters_json) : {};
                await api.put('/api/user/settings/report-schedules', {
                  enabled: Boolean(s.enabled),
                  cadence: s.cadence || 'weekly',
                  delivery_date: s.delivery_date || '',
                  delivery_time: s.delivery_time || '08:00',
                  recipient_emails: s.recipient_emails || '',
                  filters_json: JSON.stringify({
                    theme: filters.theme || '',
                    sentiment: filters.sentiment || 'all'
                  })
                });
                await refreshCurrentSchedule();
                notifySuccess('Schedule restored');
                closeToast();
              } catch (restoreErr) {
                notifyError(restoreErr.response?.data?.error || 'Failed to restore schedule');
              }
            }}
            className="btn btn-sm btn-outline"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 10px' }}
          >
            <Undo2 size={14} />
            Undo
          </button>
        </div>
      ), { autoClose: 5000 });
    } catch (err) {
      notifyError(err?.response?.data?.error || 'Failed to delete schedule');
    }
  };

  const clearAllScopedSchedules = async () => {
    // scope: 'all' -> aggregated clear (super_admin only)
    // scope: 'my' -> clear schedules for current account (delete each schedule)
    const result = await confirm({
      title: scope === 'all' ? 'Clear Aggregated Schedules' : 'Clear My Schedules',
      message: scope === 'all'
        ? 'Clear all aggregated report schedules? This will soft-delete every visible schedule in the aggregate report.'
        : 'Clear all schedules for your account? This will soft-delete your saved schedules.',
      actions: [{ label: 'Clear', value: 'clear', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'clear') return;

    setClearingAll(true);
    try {
      if (scope === 'all') {
        const resp = await api.post('/api/admin/report-schedules/clear-all');
        notifySuccess(resp.data?.message || 'All aggregated schedules cleared');
        await refreshAggregatedSchedules();
      } else {
        // Clear current user's schedules by deleting history entries
        const hist = history || [];
        // include current schedule if it has an id
        const ids = hist.map(h => h.schedule_id).filter(Boolean);
        if (schedule && schedule.schedule_id) ids.push(schedule.schedule_id);
        // ensure unique
        const uniq = Array.from(new Set(ids));
        for (const id of uniq) {
          try {
            await api.delete(`/api/user/settings/report-schedules/${id}`);
          } catch (e) {
            console.warn('Failed deleting schedule id', id, e);
          }
        }
        notifySuccess('Your schedules were cleared');
        await refreshCurrentSchedule();
      }
    } catch (err) {
      notifyError(err.response?.data?.error || 'Failed to clear schedules');
    } finally {
      setClearingAll(false);
    }
  };

  if (loading) return <div className="card card-body">Loading scheduled reports...</div>;
  if (error) return <div className="card card-body text-danger">{error}</div>;

const renderTableRow = (s, idx) => {
    const { statusValue, statusStyle } = getDisplayDeliveryStatus(s);
    return (
      <tr key={s.schedule_id || `${s.updated_at || ''}-${s.delivery_time || ''}-${idx}`}>
        <td>{s.enabled ? 'Yes' : 'No'}</td>
        <td>{s.cadence}</td>
        <td>{s.delivery_date || '-'}</td>
        <td>{formatTime12Hr(s.delivery_time)}</td>
        <td style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 220 }}>{s.recipient_emails || '(none)'}</td>
        <td style={{ maxWidth: 300, whiteSpace: 'normal' }}>{formatFilters(s.filters_json)}</td>
        <td>
          <span style={statusStyle}>{statusValue}</span>
          <div style={{ marginTop: 4, fontSize: '0.75rem', color: '#666', maxWidth: 260, whiteSpace: 'normal' }}>
            {getLastSendResult(s)}
          </div>
        </td>
        <td style={{ fontSize: '0.85rem' }}>{s.last_delivery_at ? new Date(s.last_delivery_at).toLocaleString() : 'Never'}</td>
        <td>{s.created_at ? new Date(s.created_at).toLocaleString() : '-'}</td>
        <td style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm btn-outline" onClick={() => openEditModal(s)}>Edit</button>
          <button
            className="btn btn-sm btn-danger"
            onClick={() => deleteSchedule(s)}
            disabled={!s.schedule_id}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <Trash2 size={14} />
            Delete
          </button>
        </td>
      </tr>
    );
  };

  const rows = (history && history.length > 0) ? history : (schedule ? [Object.assign({ schedule_id: 'current' }, schedule)] : []);
  const visibleAggregatedGroups = getAggregatedRowsByScope();

  return (
    <div className="dashboard">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 className="page-title">Scheduled Reports</h1>
          <p className="page-subtitle">Saved schedules for your account (most recent first)</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
          <div className="button-group" style={{ justifyContent: 'flex-end' }}>
            {(user?.role === 'admin' || user?.role === 'super_admin') && (
              <button
                type="button"
                className={autoRefresh ? 'btn btn-success' : 'btn btn-outline'}
                onClick={() => setAutoRefresh(!autoRefresh)}
              >
                {autoRefresh ? 'Auto Refresh: ON' : 'Auto Refresh: OFF'}
              </button>
            )}
            <button className="btn btn-outline" onClick={() => navigate('/reports')}>Back to Reports</button>
            <button className="btn btn-primary" onClick={() => navigate('/settings#report-schedule-settings')}>Schedule Delivery</button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-body">
          {rows.length === 0 ? (
            <div className="empty-state">
              <h4>No scheduled report configured</h4>
              <p>You can enable and save a scheduled report in <a href="/settings#report-schedule-settings">Settings</a>.</p>
            </div>
          ) : (
            <div className="table-container">
              <table className="table">
<thead>
                  <tr>
                    <th>Enabled</th>
                    <th>Cadence</th>
                    <th>Delivery Date</th>
                    <th>Delivery Time</th>
                    <th>Recipients</th>
                    <th>Filters</th>
                    <th>Last Status</th>
                    <th>Last Delivery</th>
                    <th>Created</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => renderTableRow(r, i))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* SuperAdmin Aggregated Schedules */}
      {user?.role === 'super_admin' && aggregatedSchedules && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="card-header" style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
            <div>
              <h3>Aggregated Schedules from All Roles</h3>
              <p style={{ fontSize: '0.9rem', color: '#666', marginTop: 4 }}>View report delivery schedules from all editors, admins, and super admins</p>
              <div style={{ marginTop: 6, fontSize: '0.85rem', color: '#666' }}>
                Last update: {lastRefresh || 'Never'}
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
              <div style={{ display: 'inline-flex', borderRadius: 8, overflow: 'hidden', border: '1px solid #e6e6e6' }}>
                <button
                  className={"btn " + (scope === 'all' ? 'btn-primary' : 'btn-outline')}
                  onClick={() => setScope('all')}
                  style={{ borderRadius: 0, padding: '6px 12px' }}
                >
                  All Users
                </button>
                <button
                  className={"btn " + (scope === 'my' ? 'btn-primary' : 'btn-outline')}
                  onClick={() => setScope('my')}
                  style={{ borderRadius: 0, padding: '6px 12px' }}
                >
                  My Account
                </button>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
                <button className="btn btn-outline" onClick={refreshAggregatedSchedules} disabled={isRefreshing}>
                  {isRefreshing ? 'Refreshing...' : 'Refresh'}
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={clearAllScopedSchedules}
                  disabled={clearingAll || !visibleAggregatedGroups.length}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
                >
                  <X size={14} />
                  {clearingAll ? 'Clearing...' : (scope === 'all' ? 'Clear All' : 'Clear My')}
                </button>
              </div>
            </div>
          </div>
          <div className="card-body">
            {!visibleAggregatedGroups.length ? (
              <div className="empty-state">
                <p>{scope === 'all' ? 'No aggregated schedules found from other users.' : 'No schedules found for your account.'}</p>
              </div>
            ) : (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>User</th>
                      <th>Role</th>
                      <th>Enabled</th>
                      <th>Cadence</th>
                      <th>Delivery Time</th>
                      <th>Recipients</th>
                      <th>Last Status</th>
                      <th>Last Delivery</th>
                      <th>Deleted</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleAggregatedGroups.map((userGroup) =>
                      userGroup.schedules.map((schedule) => (
                        <tr key={schedule.schedule_id}>
                          <td style={{ fontSize: '0.85rem' }}>{schedule.schedule_id}</td>
                          <td><strong>{userGroup.username}</strong></td>
                          <td><span style={{ padding: '4px 8px', borderRadius: 4, background: '#f0f0f0' }}>{userGroup.role}</span></td>
                          <td>{schedule.enabled ? '✓' : '✗'}</td>
                          <td>{schedule.cadence || 'N/A'}</td>
                          <td>{formatTime12Hr(schedule.delivery_time)}</td>
                          <td style={{ fontSize: '0.85rem' }}>{schedule.recipient_emails ? schedule.recipient_emails.split(',').slice(0, 2).join(', ') + (schedule.recipient_emails.split(',').length > 2 ? '...' : '') : 'N/A'}</td>
                          <td>
                            <span style={getDisplayDeliveryStatus(schedule).statusStyle}>{getDisplayDeliveryStatus(schedule).statusValue}</span>
                            <div style={{ marginTop: 4, fontSize: '0.75rem', color: '#666', maxWidth: 260, whiteSpace: 'normal' }}>
                              {getLastSendResult(schedule)}
                            </div>
                          </td>
                          <td style={{ fontSize: '0.85rem' }}>{schedule.last_delivery_at ? new Date(schedule.last_delivery_at).toLocaleString() : 'Never'}</td>
                          <td>{schedule.is_deleted ? `Yes${schedule.deleted_at ? ' ' + new Date(schedule.deleted_at).toLocaleString() : ''}` : 'No'}</td>
                          <td style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                            {schedule.is_deleted ? (
                              <button className="btn btn-sm btn-success" onClick={async () => {
                                try {
                                  await api.post(`/api/admin/report-schedules/${schedule.schedule_id}/restore`);
                                  notifySuccess('Schedule restored');
                                  await refreshAggregatedSchedules();
                                } catch (err) {
                                  notifyError(err.response?.data?.error || 'Failed to restore');
                                }
                              }}>Restore</button>
                            ) : (
                              <button className="btn btn-sm btn-danger" onClick={async () => {
                                const result = await confirm({
                                  title: 'Purge Schedule',
                                  message: 'Permanently purge this schedule? This cannot be undone.',
                                  actions: [{ label: 'Purge', value: 'purge', variant: 'danger' }],
                                  cancelLabel: 'Cancel',
                                });
                                if (result.action !== 'purge') return;
                                try {
                                  await api.delete(`/api/admin/report-schedules/${schedule.schedule_id}/purge`);
                                  notifySuccess('Schedule purged');
                                  await refreshAggregatedSchedules();
                                } catch (err) {
                                  notifyError(err.response?.data?.error || 'Failed to purge');
                                }
                              }}>Purge</button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editModalOpen && editingSchedule && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999
        }}>
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 24,
            maxWidth: 600,
            width: '90%',
            maxHeight: '90vh',
            overflow: 'auto',
            boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2>Edit Schedule</h2>
              <button onClick={closeEditModal} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                <X size={24} />
              </button>
            </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Enabled</label>
                <select value={editingSchedule.enabled ? '1' : '0'} onChange={(e) => setEditingSchedule({ ...editingSchedule, enabled: e.target.value === '1' })} className="form-select">
                  <option value="1">Yes</option>
                  <option value="0">No</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Cadence</label>
                <select value={editingSchedule.cadence} onChange={(e) => setEditingSchedule({ ...editingSchedule, cadence: e.target.value })} className="form-select">
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Delivery Date</label>
                <input type="date" value={editingSchedule.delivery_date} onChange={(e) => setEditingSchedule({ ...editingSchedule, delivery_date: e.target.value })} className="form-input" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Delivery Time</label>
                <input type="time" value={editingSchedule.delivery_time} onChange={(e) => setEditingSchedule({ ...editingSchedule, delivery_time: e.target.value })} className="form-input" />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Recipients (comma-separated)</label>
                <input type="text" value={editingSchedule.recipient_emails} onChange={(e) => setEditingSchedule({ ...editingSchedule, recipient_emails: e.target.value })} className="form-input" placeholder="ops@example.com, admin@example.com" />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Theme</label>
                <select value={editingSchedule.theme} onChange={(e) => setEditingSchedule({ ...editingSchedule, theme: e.target.value })} className="form-select">
                  <option value="">All themes</option>
                  {themes.map((th) => (
                    <option key={th} value={th}>{th}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>Sentiment</label>
                <select value={editingSchedule.sentiment} onChange={(e) => setEditingSchedule({ ...editingSchedule, sentiment: e.target.value })} className="form-select">
                  <option value="all">All</option>
                  <option value="positive">Positive</option>
                  <option value="neutral">Neutral</option>
                  <option value="negative">Negative</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={closeEditModal} disabled={saving}>Cancel</button>
              <button className="btn btn-primary" onClick={saveEdit} disabled={saving}>{saving ? 'Saving...' : 'Save Changes'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ScheduledReports;
