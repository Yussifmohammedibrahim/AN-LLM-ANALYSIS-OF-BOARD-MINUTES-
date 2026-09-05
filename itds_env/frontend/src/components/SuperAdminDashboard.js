import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ShieldCheck, RotateCcw, Users, FileWarning, ShieldPlus, CalendarDays, Mic, Radar } from 'lucide-react';
import { adminAPI, aiAPI, dataAPI } from '../api/api';
import { SelectionProvider, useSelection } from './selection/SelectionContext';
import BulkActionsBar from './BulkActionsBar';
import { useAuth } from '../context/AuthContext';
import { ensureArray } from '../utils/safeMap';
import { notifyError, notifySuccess } from '../utils/notify';
import { usePrompt } from './ConfirmProvider';
import './SuperAdminDashboard.css';

const formatTimestamp = (value) => {
  if (!value) return 'N/A';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'N/A' : parsed.toLocaleString();
};

const textPreview = (value, max = 90) => {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return 'N/A';
  return normalized.length > max ? `${normalized.slice(0, max)}...` : normalized;
};

const SuperAdminDashboard = () => {
  const { isSuperAdmin, user } = useAuth();
  const prompt = usePrompt();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState('');
  const [loadWarning, setLoadWarning] = useState('');
  const [users, setUsers] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  const [deletedMeetings, setDeletedMeetings] = useState([]);
  const [busyKey, setBusyKey] = useState('');
  const [activeTab, setActiveTab] = useState('promote');
  const [meetings, setMeetings] = useState([]);
  const [healthMetric, setHealthMetric] = useState(null);
  const [deletedUserSearch, setDeletedUserSearch] = useState('');
  const [activeUserSearch, setActiveUserSearch] = useState('');
  const [activeRoleFilter, setActiveRoleFilter] = useState('all');
  const [deletedTranscriptSearch, setDeletedTranscriptSearch] = useState('');
  const [promoteSearch, setPromoteSearch] = useState('');
  const inFlightRef = useRef(false);

  const loadData = useCallback(async ({ silent = false, source = 'auto', force = false } = {}) => {
    if (inFlightRef.current) {
      return;
    }

    inFlightRef.current = true;

    if (!silent) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      setLoadWarning('');
      const nonce = force ? Date.now() : undefined;
      const [usersRes, transcriptRes, meetingsRes, deletedMeetingsRes, healthRes] = await Promise.allSettled([
        adminAPI.getUsers({ include_deleted: 1, ...(nonce ? { _ts: nonce } : {}) }),
        aiAPI.getTranscripts({ include_deleted: 1, ...(nonce ? { _ts: nonce } : {}) }),
        dataAPI.getMeetings({ limit: 1000, ...(nonce ? { _ts: nonce } : {}) }),
        aiAPI.getDeletedMeetings(nonce ? { _ts: nonce } : {}),
        adminAPI.getSystemHealth()
      ]);

      let warning = '';

      if (usersRes.status === 'fulfilled') {
        setUsers(ensureArray(usersRes.value.data));
      } else {
        warning = 'Users data could not be refreshed. Showing previous values where available.';
      }

      if (transcriptRes.status === 'fulfilled') {
        setTranscripts(ensureArray(transcriptRes.value.data?.transcripts));
      } else {
        warning = warning || 'Minutes and recordings could not be refreshed. Showing previous values where available.';
      }

      if (meetingsRes?.status === 'fulfilled') {
        setMeetings(ensureArray(meetingsRes.value.data?.meetings));
      } else if (meetingsRes?.status === 'rejected') {
        warning = warning || 'Meetings data could not be refreshed. Showing previous values where available.';
      }

      if (deletedMeetingsRes?.status === 'fulfilled') {
        setDeletedMeetings(ensureArray(deletedMeetingsRes.value.data?.meetings));
      } else if (deletedMeetingsRes?.status === 'rejected') {
        const status = deletedMeetingsRes.reason?.response?.status;
        // Backward-compatible fallback: older backends may not expose this endpoint yet.
        if (status === 404 || status === 405) {
          setDeletedMeetings([]);
        } else {
          warning = warning || 'Deleted meeting snapshots could not be refreshed. Showing previous values where available.';
        }
      }

      if (healthRes?.status === 'fulfilled') {
        const backendHealth = Number(healthRes.value.data?.health_percentage);
        setHealthMetric(Number.isFinite(backendHealth) ? backendHealth : null);
      } else if (healthRes?.status === 'rejected') {
        setHealthMetric(null);
        warning = warning || 'System health metric could not be refreshed. Showing fallback status.';
      }

      if (warning) {
        setLoadWarning(warning);
        notifyError(warning);
      } else if (source === 'manual') {
        notifySuccess('Super Admin dashboard refreshed.');
      }
      setLastSyncedAt(new Date().toISOString());
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to load super admin recovery data.');
    } finally {
      setLoading(false);
      setRefreshing(false);
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (!isSuperAdmin()) {
      return;
    }
    loadData({ force: true });
  }, [isSuperAdmin, loadData]);

// --- Selection helpers for deleted transcripts ---
const DeletedSelectAll = ({ results = [] }) => {
  const { selected, selectAll, clear } = useSelection();
  const allIds = results.map((r) => String(r.transcript_id));
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
  const someSelected = allIds.some((id) => selected.has(id));
  return (
    <input type="checkbox" aria-label="Select all deleted transcripts" checked={allSelected} ref={(el) => { if (el) el.indeterminate = !allSelected && someSelected; }} onChange={(e) => e.target.checked ? selectAll(allIds) : clear()} />
  );
};

const DeletedTranscriptRow = ({ item, busyKey, onRestore, onPurge }) => {
  const id = String(item.transcript_id);
  const { selected, toggle } = useSelection();
  const isSelected = selected.has(id);
  return (
    <tr tabIndex={0} className={isSelected ? 'row-selected' : ''} aria-selected={isSelected}>
      <td>
        <input type="checkbox" aria-label={`Select transcript ${id}`} checked={isSelected} onChange={() => toggle(id)} onClick={(e) => e.stopPropagation()} />
      </td>
      <td>{item.transcript_id}</td>
      <td className="super-admin-text-preview">{textPreview(item.transcript_text)}</td>
      <td>{formatTimestamp(item.deleted_at)}</td>
      <td>{item.delete_reason || 'N/A'}</td>
      <td>
        <div className="button-group">
          <button className="btn btn-success btn-sm" onClick={() => onRestore(item.transcript_id)} disabled={busyKey === `restore-transcript-${item.transcript_id}`}>
            {busyKey === `restore-transcript-${item.transcript_id}` ? 'Restoring...' : 'Restore'}
          </button>
          <button className="btn btn-danger btn-sm" onClick={() => onPurge(item.transcript_id)} disabled={busyKey === `purge-transcript-${item.transcript_id}`}>
            {busyKey === `purge-transcript-${item.transcript_id}` ? 'Purging...' : 'Purge'}
          </button>
        </div>
      </td>
    </tr>
  );
};

  const deletedUsers = useMemo(() => users.filter((item) => Boolean(item.is_deleted)), [users]);
  const activeUsers = useMemo(() => users.filter((item) => !item.is_deleted), [users]);
  const activeTranscripts = useMemo(() => transcripts.filter((item) => !item.is_deleted), [transcripts]);
  const deletedTranscripts = useMemo(() => transcripts.filter((item) => Boolean(item.is_deleted)), [transcripts]);

  const filteredDeletedUsers = useMemo(() => {
    const q = deletedUserSearch.trim().toLowerCase();
    if (!q) return deletedUsers;
    return deletedUsers.filter((item) =>
      [item.username, item.role, item.delete_reason].some((value) => String(value || '').toLowerCase().includes(q))
    );
  }, [deletedUsers, deletedUserSearch]);

  const filteredActiveUsers = useMemo(() => {
    const q = activeUserSearch.trim().toLowerCase();
    return activeUsers.filter((item) => {
      const roleMatch = activeRoleFilter === 'all' ? true : item.role === activeRoleFilter;
      const queryMatch = !q ? true : [item.username, item.role, item.email].some((value) => String(value || '').toLowerCase().includes(q));
      return roleMatch && queryMatch;
    });
  }, [activeUsers, activeUserSearch, activeRoleFilter]);

  const filteredDeletedTranscripts = useMemo(() => {
    const q = deletedTranscriptSearch.trim().toLowerCase();
    if (!q) return deletedTranscripts;
    return deletedTranscripts.filter((item) =>
      [item.transcript_id, item.transcript_text, item.delete_reason].some((value) => String(value || '').toLowerCase().includes(q))
    );
  }, [deletedTranscripts, deletedTranscriptSearch]);

  const promotionCandidates = useMemo(() => {
    const candidates = activeUsers.filter((item) => item.user_id !== user?.user_id && item.role !== 'super_admin');
    const q = promoteSearch.trim().toLowerCase();
    if (!q) return candidates;
    return candidates.filter((item) =>
      [item.username, item.email, item.role].some((value) => String(value || '').toLowerCase().includes(q))
    );
  }, [activeUsers, promoteSearch, user?.user_id]);

  const stats = useMemo(() => ({
    totalUsers: users.length,
    deletedUsers: deletedUsers.length,
    totalTranscripts: transcripts.length,
    deletedTranscripts: deletedTranscripts.length,
    totalMeetings: meetings.length,
    totalRecordings: activeTranscripts.length,
    activeHealth: Number.isFinite(healthMetric) ? Math.max(0, Math.min(100, healthMetric)) : null
  }), [users.length, deletedUsers.length, transcripts.length, deletedTranscripts.length, activeTranscripts.length, meetings.length, healthMetric]);

  const handleRestoreDeletedMeeting = async (meetingId) => {
    const opKey = `restore-meeting-${meetingId}`;
    setBusyKey(opKey);
    try {
      await aiAPI.restoreDeletedMeetingMinute(meetingId);
      notifySuccess('Deleted meeting minute restored successfully.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to restore deleted meeting minute.');
    } finally {
      setBusyKey('');
    }
  };

  const handleRestoreUser = async (userId) => {
    const opKey = `restore-user-${userId}`;
    setBusyKey(opKey);
    try {
      await adminAPI.restoreUser(userId);
      notifySuccess('User restored successfully.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to restore user.');
    } finally {
      setBusyKey('');
    }
  };

  const handlePurgeUser = async (userId) => {
    const result = await prompt({
      title: 'Purge User',
      message: 'Type PURGE USER to permanently delete this account.',
      inputLabel: 'Confirmation phrase',
      placeholder: 'PURGE USER',
      submitLabel: 'Purge',
      cancelLabel: 'Cancel',
      validate: (value) => (value === 'PURGE USER' ? true : 'Phrase does not match.'),
    });
    if (result.action !== 'submit') return;

    const opKey = `purge-user-${userId}`;
    setBusyKey(opKey);
    try {
      await adminAPI.purgeUser(userId);
      notifySuccess('User permanently deleted.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to permanently delete user.');
    } finally {
      setBusyKey('');
    }
  };

  const handleRoleChange = async (userId, nextRole) => {
    const target = activeUsers.find((item) => item.user_id === userId);
    if (!target || target.role === nextRole) return;

    const opKey = `role-user-${userId}`;
    setBusyKey(opKey);
    try {
      await adminAPI.updateUser(userId, { role: nextRole });
      notifySuccess('User role updated.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to update role.');
    } finally {
      setBusyKey('');
    }
  };

  const handlePromoteToSuperAdmin = async (userId) => {
    const target = activeUsers.find((item) => item.user_id === userId);
    if (!target || target.role === 'super_admin') return;

    const opKey = `promote-user-${userId}`;
    setBusyKey(opKey);
    try {
      await adminAPI.updateUser(userId, { role: 'super_admin' });
      notifySuccess(`${target.username} promoted to Super Admin.`);
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to promote user.');
    } finally {
      setBusyKey('');
    }
  };

  const handleRestoreTranscript = async (transcriptId) => {
    const opKey = `restore-transcript-${transcriptId}`;
    setBusyKey(opKey);
    try {
      await aiAPI.restoreTranscript(transcriptId);
      notifySuccess('Minute/recording restored successfully.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to restore minute/recording.');
    } finally {
      setBusyKey('');
    }
  };

  const handlePurgeTranscript = async (transcriptId) => {
    const result = await prompt({
      title: 'Purge Recording',
      message: 'Type PURGE RECORDING to permanently delete this item.',
      inputLabel: 'Confirmation phrase',
      placeholder: 'PURGE RECORDING',
      submitLabel: 'Purge',
      cancelLabel: 'Cancel',
      validate: (value) => (value === 'PURGE RECORDING' ? true : 'Phrase does not match.'),
    });
    if (result.action !== 'submit') return;

    const opKey = `purge-transcript-${transcriptId}`;
    setBusyKey(opKey);
    try {
      await aiAPI.deleteTranscript(transcriptId, { permanent: 1 });
      notifySuccess('Minute/recording permanently deleted.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to permanently delete minute/recording.');
    } finally {
      setBusyKey('');
    }
  };

  const handleHardDeleteAllSystemMinutes = async () => {
    const stepOne = await prompt({
      title: 'Step 1 of 2',
      message: 'Type PURGE DELETED ONLY to permanently delete only deleted minutes and recordings.',
      inputLabel: 'First confirmation phrase',
      placeholder: 'PURGE DELETED ONLY',
      submitLabel: 'Continue',
      cancelLabel: 'Cancel',
      validate: (value) => (value === 'PURGE DELETED ONLY' ? true : 'Phrase does not match.'),
    });
    if (stepOne.action !== 'submit') return;

    const stepTwo = await prompt({
      title: 'Step 2 of 2',
      message: 'Final confirmation: Type PERMANENT DELETE to continue. Active meetings/recordings will not be touched.',
      inputLabel: 'Final confirmation phrase',
      placeholder: 'PERMANENT DELETE',
      submitLabel: 'Permanently Delete',
      cancelLabel: 'Cancel',
      validate: (value) => (value === 'PERMANENT DELETE' ? true : 'Phrase does not match.'),
    });
    if (stepTwo.action !== 'submit') return;

    const opKey = 'hard-delete-system-minutes';
    setBusyKey(opKey);
    try {
      await aiAPI.hardDeleteAllMinutesAndRecordings();
      notifySuccess('All deleted minutes and recordings were permanently purged. Active records were preserved.');
      await loadData({ silent: true, source: 'action', force: true });
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to permanently purge deleted minutes and recordings.');
    } finally {
      setBusyKey('');
    }
  };

  if (!isSuperAdmin()) {
    return (
      <div className="page-content">
        <div className="dashboard">
          <div className="card">
            <div className="card-body">
              <p>Super admin access is required.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="loading min-h-screen"><div className="spinner"></div></div>;
  }

  const tabs = [
    { id: 'promote', label: 'Promote to Super Admin', icon: ShieldPlus },
    { id: 'deleted-users', label: 'Deleted Users', icon: Users },
    { id: 'role-recovery', label: 'Role Recovery', icon: ShieldCheck },
    { id: 'deleted-transcripts', label: 'Deleted Minutes', icon: FileWarning }
  ];

  return (
    <div className="page-content super-admin-page">
      <div className="dashboard">
        <div className="dashboard-header super-admin-header">
          <div>
            <h1 className="dashboard-title">Super Admin Dashboard</h1>
            <p className="dashboard-subtitle">Emergency recovery, deleted records, and privilege controls in one place.</p>
          </div>
          <button
            className="btn btn-outline super-admin-refresh-btn"
            onClick={() => loadData({ silent: true, source: 'manual', force: true })}
            disabled={refreshing}
            aria-busy={refreshing}
          >
            <RotateCcw size={16} className={refreshing ? 'super-admin-refresh-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh Data'}
          </button>
        </div>

        <div className="super-admin-meta-row">
          <p className="text-xs text-secondary">Last synced: {formatTimestamp(lastSyncedAt)}</p>
          {loadWarning ? <p className="text-xs super-admin-warning">{loadWarning}</p> : <p className="text-xs super-admin-status-ok">All systems synced</p>}
        </div>

        {/* Summary Stats Card */}
        <div className="card super-admin-summary-card">
          <div className="super-admin-kpi-grid">
            <div className="super-admin-kpi-card">
              <div className="super-admin-kpi-icon super-admin-kpi-icon-blue">
                <Users size={18} />
              </div>
              <div className="super-admin-kpi-content">
                <div className="super-admin-kpi-value">{stats.totalUsers}</div>
                <div className="super-admin-kpi-label">Users</div>
                <div className="super-admin-kpi-meta">Deleted: <span className="super-admin-kpi-meta-danger">{stats.deletedUsers}</span></div>
              </div>
            </div>

            <div className="super-admin-kpi-card">
              <div className="super-admin-kpi-icon super-admin-kpi-icon-blue">
                <CalendarDays size={18} />
              </div>
              <div className="super-admin-kpi-content">
                <div className="super-admin-kpi-value">{stats.totalMeetings}</div>
                <div className="super-admin-kpi-label">Meetings</div>
                <div className="super-admin-kpi-meta">Deleted: <span className="super-admin-kpi-meta-danger">{stats.deletedTranscripts}</span></div>
              </div>
            </div>

            <div className="super-admin-kpi-card">
              <div className="super-admin-kpi-icon super-admin-kpi-icon-green">
                <Mic size={18} />
              </div>
              <div className="super-admin-kpi-content">
                <div className="super-admin-kpi-value">{stats.totalRecordings}</div>
                <div className="super-admin-kpi-label">Recordings</div>
                <div className="super-admin-kpi-meta">Deleted: <span className="super-admin-kpi-meta-danger">{stats.deletedTranscripts}</span></div>
              </div>
            </div>

            <div className="super-admin-kpi-card super-admin-kpi-card-health">
              <div className="super-admin-kpi-icon super-admin-kpi-icon-green">
                <Radar size={18} />
              </div>
              <div className="super-admin-kpi-content">
                <div className="super-admin-kpi-value">{stats.activeHealth == null ? 'N/A' : `${stats.activeHealth}%`}</div>
                <div className="super-admin-kpi-label">Active Health</div>
                <div className="super-admin-kpi-meta">System status</div>
                <div className="super-admin-health-bar" aria-hidden="true">
                  <div
                    className="super-admin-health-usage"
                    style={{ width: `${stats.activeHealth == null ? 0 : stats.activeHealth}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="super-admin-tabs">
          {tabs.map((tab) => {
            const TabIcon = tab.icon;
            return (
              <button
                key={tab.id}
                className={`super-admin-tab ${activeTab === tab.id ? 'super-admin-tab-active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <TabIcon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        {activeTab === 'promote' && (
          <div className="card super-admin-elevated-card super-admin-tab-content">
            <div className="card-header">
              <div>
                <h3 className="card-title">Promote to Super Admin</h3>
                <p className="super-admin-card-hint">One-click privilege escalation for trusted administrators.</p>
              </div>
              <span className="super-admin-chip">{promotionCandidates.length} candidates</span>
            </div>
            <div className="card-body">
              <div className="super-admin-toolbar">
                <input
                  className="form-input"
                  placeholder="Search by username or email"
                  value={promoteSearch}
                  onChange={(event) => setPromoteSearch(event.target.value)}
                />
              </div>
              {promotionCandidates.length === 0 ? (
                <div className="super-admin-empty">No promotion candidates found. All non-super-admin users are already promoted or match your filters.</div>
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Current Role</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {promotionCandidates.map((item) => (
                        <tr key={item.user_id}>
                          <td>{item.username}</td>
                          <td>{item.email || 'N/A'}</td>
                          <td><span className="super-admin-role-badge">{item.role}</span></td>
                          <td>
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handlePromoteToSuperAdmin(item.user_id)}
                              disabled={busyKey === `promote-user-${item.user_id}`}
                              title="Promote this user to Super Admin"
                            >
                              <ShieldPlus size={14} />
                              {busyKey === `promote-user-${item.user_id}` ? 'Promoting...' : 'Promote'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'deleted-users' && (
          <div className="card super-admin-elevated-card super-admin-tab-content">
            <div className="card-header">
              <div>
                <h3 className="card-title">Deleted Users Recovery</h3>
                <p className="super-admin-card-hint">Restore or permanently purge user accounts with full audit trace.</p>
              </div>
              <span className="super-admin-chip">{filteredDeletedUsers.length}/{deletedUsers.length} items</span>
            </div>
            <div className="card-body">
              <div className="super-admin-toolbar">
                <input
                  className="form-input"
                  placeholder="Search deleted users by username, role, or reason"
                  value={deletedUserSearch}
                  onChange={(event) => setDeletedUserSearch(event.target.value)}
                />
              </div>
              {filteredDeletedUsers.length === 0 ? (
                <div className="super-admin-empty">No deleted users found.</div>
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Username</th>
                        <th>Role</th>
                        <th>Deleted At</th>
                        <th>Reason</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDeletedUsers.map((item) => (
                        <tr key={item.user_id}>
                          <td>{item.username}</td>
                          <td>{item.role}</td>
                          <td>{formatTimestamp(item.deleted_at)}</td>
                          <td>{item.delete_reason || 'N/A'}</td>
                          <td>
                            <div className="button-group">
                              <button
                                className="btn btn-success btn-sm"
                                onClick={() => handleRestoreUser(item.user_id)}
                                disabled={busyKey === `restore-user-${item.user_id}`}
                              >
                                {busyKey === `restore-user-${item.user_id}` ? 'Restoring...' : 'Restore'}
                              </button>
                              <button
                                className="btn btn-danger btn-sm"
                                onClick={() => handlePurgeUser(item.user_id)}
                                disabled={busyKey === `purge-user-${item.user_id}`}
                              >
                                {busyKey === `purge-user-${item.user_id}` ? 'Purging...' : 'Purge'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'role-recovery' && (
          <div className="card super-admin-elevated-card super-admin-tab-content">
            <div className="card-header">
              <div>
                <h3 className="card-title">Role & Privilege Recovery</h3>
                <p className="super-admin-card-hint">Quickly repair role access when permissions are misconfigured.</p>
              </div>
              <span className="super-admin-chip">{filteredActiveUsers.length}/{activeUsers.length} active users</span>
            </div>
            <div className="card-body">
              <p className="text-secondary mb-4">Reassign roles if admin permissions were misconfigured.</p>
              <div className="super-admin-toolbar super-admin-toolbar-split">
                <input
                  className="form-input"
                  placeholder="Search active users"
                  value={activeUserSearch}
                  onChange={(event) => setActiveUserSearch(event.target.value)}
                />
                <select
                  className="form-select"
                  value={activeRoleFilter}
                  onChange={(event) => setActiveRoleFilter(event.target.value)}
                >
                  <option value="all">All roles</option>
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                  <option value="admin">Admin</option>
                  <option value="super_admin">Super Admin</option>
                </select>
              </div>
              {filteredActiveUsers.length === 0 ? (
                <div className="super-admin-empty">No active users available for role recovery.</div>
              ) : (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Username</th>
                      <th>Current Role</th>
                      <th>Role</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredActiveUsers.map((item) => {
                      const isSelf = item.user_id === user?.user_id;
                      return (
                        <tr key={item.user_id}>
                          <td>{item.username}</td>
                          <td>{item.role}</td>
                          <td>
                            <select
                              className="form-select form-select-sm"
                              value={item.role}
                              disabled={isSelf || busyKey === `role-user-${item.user_id}`}
                              title={isSelf ? 'Cannot change your own role' : ''}
                              onChange={(event) => handleRoleChange(item.user_id, event.target.value)}
                            >
                              <option value="viewer">Viewer</option>
                              <option value="editor">Editor</option>
                              <option value="admin">Admin</option>
                              <option value="super_admin">Super Admin</option>
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'deleted-transcripts' && (
          <div className="card super-admin-elevated-card super-admin-tab-content">
            <div className="card-header">
              <div>
                <h3 className="card-title">Deleted Minutes & Recordings Recovery</h3>
                <p className="super-admin-card-hint">Bring deleted records back or remove them permanently with confirmation.</p>
              </div>
              <div className="button-group">
                <span className="super-admin-chip">{filteredDeletedTranscripts.length}/{deletedTranscripts.length} items</span>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={handleHardDeleteAllSystemMinutes}
                  disabled={busyKey === 'hard-delete-system-minutes'}
                  title="Permanently delete only deleted minutes/recordings and deleted meeting snapshots"
                >
                  {busyKey === 'hard-delete-system-minutes' ? 'Purging Deleted...' : 'Permanent Delete All'}
                </button>
              </div>
            </div>
            <div className="card-body">
            <p className="text-xs text-secondary mb-3">Danger zone: Permanent Delete All removes only deleted minutes/recordings and deleted meeting snapshots with no recovery. Active records are not affected.</p>
            <div className="super-admin-toolbar">
              <input
                className="form-input"
                placeholder="Search by transcript ID, text preview, or reason"
                value={deletedTranscriptSearch}
                onChange={(event) => setDeletedTranscriptSearch(event.target.value)}
              />
            </div>
            {filteredDeletedTranscripts.length === 0 ? (
              <div className="super-admin-empty">No deleted minutes/recordings found.</div>
            ) : (
              <SelectionProvider>
                <BulkActionsBar itemsMap={filteredDeletedTranscripts.slice(0,60).reduce((acc,r)=>{ acc[String(r.transcript_id)] = r; return acc; },{})} onDeleteComplete={() => loadData({ silent: true, force: true })} />
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>
                          <DeletedSelectAll results={filteredDeletedTranscripts.slice(0,60)} />
                        </th>
                        <th>ID</th>
                        <th>Preview</th>
                        <th>Deleted At</th>
                        <th>Reason</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDeletedTranscripts.slice(0, 60).map((item) => (
                        <DeletedTranscriptRow key={item.transcript_id} item={item} busyKey={busyKey} onRestore={handleRestoreTranscript} onPurge={handlePurgeTranscript} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </SelectionProvider>
            )}

            <div className="mt-4">
              <h4 className="card-title" style={{ marginBottom: '0.75rem' }}>Deleted Meeting Minutes (Cleared Uploads)</h4>
              {deletedMeetings.length === 0 ? (
                <div className="super-admin-empty">No deleted uploaded meeting minutes found.</div>
              ) : (
                <div className="table-container">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Meeting ID</th>
                        <th>Source File</th>
                        <th>Meeting Date</th>
                        <th>Deleted At</th>
                        <th>Segments</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deletedMeetings.slice(0, 60).map((item) => (
                        <tr key={item.snapshot_id || item.meeting_id}>
                          <td>{item.meeting_id}</td>
                          <td>{item.source_filename || 'N/A'}</td>
                          <td>{item.meeting_date || 'N/A'}</td>
                          <td>{formatTimestamp(item.deleted_at)}</td>
                          <td>{item.segments_count ?? 0}</td>
                          <td>
                            <button
                              className="btn btn-success btn-sm"
                              onClick={() => handleRestoreDeletedMeeting(item.meeting_id)}
                              disabled={busyKey === `restore-meeting-${item.meeting_id}`}
                            >
                              {busyKey === `restore-meeting-${item.meeting_id}` ? 'Restoring...' : 'Restore Minute'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SuperAdminDashboard;
