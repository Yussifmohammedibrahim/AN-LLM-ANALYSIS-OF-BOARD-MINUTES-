import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Navigate } from 'react-router-dom';
import { RefreshCw, Download, Clock3, ShieldCheck, Users, ChevronDown, Search, Archive, RotateCcw, ArchiveRestore } from 'lucide-react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { dataAPI, adminAPI } from '../api/api';
import { usePrompt } from './ConfirmProvider';
import { notifySuccess } from '../utils/notify';
import './ActivityLogins.css';

const formatTimestamp = (value, fallback = 'n/a') => {
  if (!value) return fallback;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
};

const eventTagClass = (action) => {
  if (action === 'login') return 'tag tag-success';
  if (action === 'logout') return 'tag tag-warning';
  if (action === 'failed_login') return 'tag tag-warning';
  return 'tag tag-neutral';
};

const statusTagClass = (status) => {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'success') return 'tag tag-success';
  if (normalized === 'failed') return 'tag tag-warning';
  return 'tag tag-neutral';
};

const archivedTagClass = (archivedAt) => {
  if (!archivedAt) return 'tag tag-success bg-success/10 text-success';
  return 'tag tag-warning bg-warning/10 text-warning';
};

const resolveLoginStatus = (record) => {
  const raw = String(record?.login_status || '').trim().toLowerCase();
  if (raw === 'success' || raw === 'failed') return raw;
  const action = String(record?.action || '').trim().toLowerCase();
  if (action === 'failed_login' || action.includes('failed')) return 'failed';
  if (action === 'login' || action === 'logout') return 'success';
  return 'unknown';
};

const parseUserAgentLite = (uaValue) => {
  const ua = String(uaValue || '').toLowerCase();
  if (!ua) return { browser: 'Unknown', os: 'Unknown', deviceType: 'desktop' };
  let browser = 'Unknown';
  if (ua.includes('edg/')) browser = 'Edge';
  else if (ua.includes('opr/') || ua.includes('opera')) browser = 'Opera';
  else if (ua.includes('chrome/')) browser = 'Chrome';
  else if (ua.includes('firefox/')) browser = 'Firefox';
  else if (ua.includes('safari/') && !ua.includes('chrome/')) browser = 'Safari';
  let os = 'Unknown';
  if (ua.includes('windows')) os = 'Windows';
  else if (ua.includes('android')) os = 'Android';
  else if (ua.includes('iphone') || ua.includes('ipad') || ua.includes('ios')) os = 'iOS';
  else if (ua.includes('mac os') || ua.includes('macintosh')) os = 'macOS';
  else if (ua.includes('linux')) os = 'Linux';
  let deviceType = 'desktop';
  if (ua.includes('ipad') || ua.includes('tablet')) deviceType = 'tablet';
  else if (ua.includes('mobile') || ua.includes('iphone') || ua.includes('android')) deviceType = 'mobile';
  return { browser, os, deviceType };
};

const resolveBrowser = (record) => record?.browser || parseUserAgentLite(record?.user_agent).browser;
const resolveOs = (record) => record?.os || parseUserAgentLite(record?.user_agent).os;
const resolveDeviceType = (record) => record?.device_type || parseUserAgentLite(record?.user_agent).deviceType;
const resolveDeviceLabel = (record) => record?.user_agent || record?.device || 'Unknown UA';

const parseDetailsObject = (detailsRaw) => {
  if (!detailsRaw) return {};
  if (typeof detailsRaw === 'object') return detailsRaw;
  if (typeof detailsRaw !== 'string') return {};
  try {
    const parsed = JSON.parse(detailsRaw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const enrichActivityRecord = (eventRecord, rawRecord) => {
  const merged = { ...(rawRecord || {}), ...(eventRecord || {}) };
  const detailsObj = parseDetailsObject((rawRecord?.details || merged.details));
  const nestedMeta = detailsObj.client_metadata && typeof detailsObj.client_metadata === 'object' ? detailsObj.client_metadata : {};
  if (!merged.id && merged.log_id) merged.id = merged.log_id;
  merged.user_agent = merged.user_agent || detailsObj.user_agent || nestedMeta.user_agent || '';
  merged.device = merged.device || detailsObj.device_name || detailsObj.device || nestedMeta.device_name || nestedMeta.device || '';
  merged.device_type = merged.device_type || detailsObj.device_type || nestedMeta.device_type || '';
  merged.browser = merged.browser || detailsObj.browser || nestedMeta.browser || '';
  merged.os = merged.os || detailsObj.os || nestedMeta.os || '';
  merged.login_status = merged.login_status || detailsObj.login_status || '';
  merged.country = merged.country || detailsObj.country || nestedMeta.country || '';
  merged.city = merged.city || detailsObj.city || nestedMeta.city || '';
  merged.region = merged.region || detailsObj.region || nestedMeta.region || '';
  if (!merged.location || String(merged.location).trim().toLowerCase() === 'unknown') {
    merged.location = detailsObj.location || nestedMeta.location || (merged.city && merged.country ? `${merged.city}, ${merged.country}` : '') || (detailsObj.timezone ? `Timezone: ${detailsObj.timezone}` : '') || (nestedMeta.timezone ? `Timezone: ${nestedMeta.timezone}` : '') || '';
  }
  return merged;
};

const ActivityLogins = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const prompt = usePrompt();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('active'); // active, archived, all
  const [filters, setFilters] = useState({ startDate: '', endDate: '', userId: '', status: '', deviceType: '', location: '' });
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [exportOpen, setExportOpen] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const exportRef = useRef(null);

  useEffect(() => {
    if (!exportOpen) return undefined;

    const handleOutsideClick = (event) => {
      if (exportRef.current && !exportRef.current.contains(event.target)) {
        setExportOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [exportOpen]);

  const loadAllUsers = useCallback(async () => {
    try {
      const response = await adminAPI.getUsers();
      const rawUsers = Array.isArray(response?.data?.users)
        ? response.data.users
        : (Array.isArray(response?.data) ? response.data : []);

      const normalizedUsers = rawUsers
        .filter((u) => u && u.user_id != null)
        .map((u) => ({ id: String(u.user_id), username: u.username || `User ${u.user_id}` }));

      setAllUsers(normalizedUsers);
    } catch {
      setAllUsers([]);
    }
  }, []);

  const fetchLogins = useCallback(async (customFilters = {}) => {
    if (refreshing && !customFilters.tab && !customFilters.manual) return;
    if (!customFilters.silent) {
      setLoading(true);
    }
    setError(null);
    try {
      const activeTab = customFilters.tab || tab;
      const params = {
        limit: 100,
        start_date: customFilters.startDate ?? filters.startDate,
        end_date: customFilters.endDate ?? filters.endDate,
        user_id: customFilters.userId ?? filters.userId,
        status: customFilters.status ?? filters.status,
        device_type: customFilters.deviceType ?? filters.deviceType,
        location: customFilters.location ?? filters.location,
        days: customFilters.days ?? 7,
        archived: activeTab === 'active' ? 'false' : activeTab === 'archived' ? 'true' : 'all',
        _ts: Date.now(),
      };
      const response = await dataAPI.getActivityLogs(params);
      const sessions = response?.data?.events || response?.data?.recent_sessions || [];
      const rawLogs = Array.isArray(response?.data?.logs) ? response.data.logs : [];
      const rawById = new Map(rawLogs.filter(row => row && (row.log_id || row.id)).map(row => [String(row.log_id || row.id), row]));
      const normalized = sessions.map((row, index) => {
        const rowId = row?.id != null ? String(row.id) : (row?.log_id != null ? String(row.log_id) : null);
        const rawMatch = (rowId && rawById.get(rowId)) || rawLogs[index] || null;
        return enrichActivityRecord(row, rawMatch);
      });
      setRecords(normalized);
      setLastUpdated(new Date());
    } catch (err) {
      const message = err?.response?.data?.error || (err?.message === 'Network Error' ? t('alBackendUnavailable') : err?.message) || t('alFetchFailed');
      setError(message);
      setRecords([]);
    } finally {
      if (!customFilters.silent) {
        setLoading(false);
      }
      setRefreshing(false);
    }
  }, [filters, tab, refreshing, t]);

  const updateFilters = (newFilters) => {
    setFilters(prev => ({ ...prev, ...newFilters }));
  };

  const clearFilters = () => {
    setFilters({ startDate: '', endDate: '', userId: '', status: '', deviceType: '', location: '' });
    setSearchTerm('');
  };

  const handleTabChange = (newTab) => {
    setTab(newTab);
    fetchLogins({ tab: newTab, silent: false });
  };

  const handleRefresh = () => {
    setRefreshing(true);
    fetchLogins({ manual: true, tab, silent: true });
  };

  const handleAutoArchive = async () => {
    try {
      await fetch('/api/admin/archive-logs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: 90 }) });
      fetchLogins({ tab: 'archived' });
    } catch (err) {
      setError(t('alArchiveFailed'));
    }
  };

  const handleClearAllLoginHistory = async () => {
    if (user?.role !== 'super_admin') {
      setError(t('alSuperAdminRequired'));
      return;
    }

    const requiredPhrase = 'PURGE LOGIN HISTORY';
    const result = await prompt({
      title: t('notificationsClearAll'),
      message: t('alPurgePrompt', { phrase: requiredPhrase }),
      inputLabel: 'Confirmation phrase',
      placeholder: requiredPhrase,
      submitLabel: t('delete'),
      cancelLabel: t('cancel'),
      validate: (value) => (value === requiredPhrase ? true : 'Phrase does not match.'),
    });
    if (result.action !== 'submit') return;

    try {
      setError(null);
      const response = await adminAPI.purgeLoginHistory(result.value);
      setSelectedIds(new Set());
      await fetchLogins({ manual: true, tab: 'active', silent: false });
      notifySuccess(response?.data?.message || t('alPurgeSuccess'));
    } catch (err) {
      setError(err?.response?.data?.error || t('alPurgeFailed'));
    }
  };

  const handleBulkAction = async (action) => {
    const ids = Array.from(selectedIds);
    if (!ids.length) return setError(t('alSelectLogsFirst'));
    try {
      const endpoint = action === 'archive' ? '/api/admin/archive-logs' : '/api/admin/restore-logs';
      const body = { log_ids: ids };
      await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      await fetchLogins({ tab, manual: true, silent: false });
      setSelectedIds(new Set());
      setError(null);
    } catch (err) {
      setError(t('alActionFailed', { action }));
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredRecords.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(filteredRecords.map(r => r.id)));
  };

  useEffect(() => {
    fetchLogins();
    loadAllUsers();
    const interval = setInterval(() => fetchLogins({ silent: true }), 15000);
    return () => clearInterval(interval);
  }, [fetchLogins, loadAllUsers]);

  const normalizedSearch = searchTerm.trim().toLowerCase();
  const filteredRecords = records.filter(record => {
    if (!normalizedSearch) return true;
    const haystack = [record.username, record.action, resolveLoginStatus(record), record.location, resolveDeviceLabel(record), resolveDeviceType(record), resolveBrowser(record), resolveOs(record), record.user_agent, record.ip_address, record.timestamp].filter(Boolean).map(String).map(s => s.toLowerCase()).join(' ');
    return haystack.includes(normalizedSearch);
  });

  const users = useMemo(() => allUsers, [allUsers]);
  const statuses = useMemo(() => Array.from(new Set(filteredRecords.map(r => resolveLoginStatus(r)))), [filteredRecords]);
  const deviceTypes = useMemo(() => Array.from(new Set(filteredRecords.map(r => resolveDeviceType(r)))), [filteredRecords]);

  if (!user) return <Navigate to="/login" replace />;

  const tableRows = filteredRecords.map(record => [
    formatTimestamp(record.timestamp, t('reportsNA')),
    record.username || t('alUnknown'),
    record.action || t('alUnknown'),
    resolveLoginStatus(record),
    record.location || t('alUnknown'),
    resolveDeviceType(record),
    `${resolveBrowser(record)} / ${resolveOs(record)}`,
    resolveDeviceLabel(record),
    record.ip_address || t('alUnknown'),
    formatTimestamp(record.archived_at || '', t('reportsNA'))
  ]);

  const loginCount = filteredRecords.filter(item => item.action === 'login').length;
  const logoutCount = filteredRecords.filter(item => item.action === 'logout').length;
  const uniqueUsersCount = new Set(filteredRecords.map(item => item.username).filter(Boolean)).size;

  const exportCsv = () => {
    const rows = [[t('alColTimestamp'), t('alColUsername'), t('alColEvent'), t('alColStatus'), t('alColLocation'), t('alColDeviceType'), t('alColBrowserOs'), t('alColDeviceAgent'), t('alColIP'), t('alColArchived')], ...tableRows];
    const csv = rows.map(row => row.map(value => `"${String(value ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `activity_logs_${tab}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    setExportOpen(false);
  };

  const exportPdf = () => {
    const doc = new jsPDF({ orientation: 'landscape' });
    doc.text(t('alPdfTitle', { tab: tab.toUpperCase() }), 14, 14);
    autoTable(doc, {
      head: [[t('alColTimestamp'), t('alColUsername'), t('alColEvent'), t('alColStatus'), t('alColLocation'), t('alColDeviceType'), t('alColBrowserOs'), t('alColDeviceAgent'), t('alColIP'), t('alColArchived')]],
      body: tableRows,
      startY: 20,
      styles: { fontSize: 7, cellPadding: 2 },
      headStyles: { fillColor: [37, 99, 235] }
    });
    doc.save(`activity_logs_${tab}.pdf`);
    setExportOpen(false);
  };

  const exportJson = () => {
    const payload = filteredRecords.map(record => ({
      id: record.id,
      timestamp: record.timestamp,
      username: record.username,
      action: record.action,
      login_status: resolveLoginStatus(record),
      location: record.location,
      device_type: resolveDeviceType(record),
      browser: resolveBrowser(record),
      os: resolveOs(record),
      ip_address: record.ip_address,
      archived_at: record.archived_at
    }));
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `activity_logs_${tab}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setExportOpen(false);
  };

  return (
    <section className="activity-logins-page">
      <div className="activity-logins-header">
        <div>
          <h2>{t('alTitle')} <span className="text-muted">({tab.toUpperCase()})</span></h2>
          <p>{t('alSubtitle')}</p>
        </div>
        <div className="activity-actions">
          <span>{t('alLastUpdated')}: {lastUpdated ? formatTimestamp(lastUpdated, t('reportsNA')) : t('alNever')}</span>
          <button className="btn btn-outline" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw size={16} className={refreshing ? 'spin' : ''} /> {t('uploadRefresh')}
          </button>
          <div className="export-dropdown" ref={exportRef}>
            <button className="btn btn-primary" onClick={() => setExportOpen(!exportOpen)} disabled={!records.length}>
              <Download size={16} /> {t('alExport')} <ChevronDown size={14} />
            </button>
            {exportOpen && (
              <div className="export-menu" role="menu" style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, boxShadow: '0 8px 24px rgba(15,23,42,0.08)', zIndex: 200 }}>
                <button className="btn btn-outline btn-sm" style={{ display: 'block', width: '100%', textAlign: 'left' }} onClick={exportCsv} role="menuitem">CSV</button>
                <button className="btn btn-outline btn-sm" style={{ display: 'block', width: '100%', textAlign: 'left' }} onClick={exportPdf} role="menuitem">PDF</button>
                <button className="btn btn-outline btn-sm" style={{ display: 'block', width: '100%', textAlign: 'left' }} onClick={exportJson} role="menuitem">JSON</button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="filters-tabs">
        <div className="tabs">
          {['active', 'archived', 'all'].map((tabKey) => (
            <button key={tabKey} className={`tab ${tab === tabKey ? 'active' : ''}`} onClick={() => handleTabChange(tabKey)}>
              {tabKey === 'active' ? t('alTabActive') : tabKey === 'archived' ? t('alTabArchived') : t('alTabAll')}
            </button>
          ))}
        </div>
      </div>

      <div className="activity-filters">
        <div className="filter-group">
          <label>{t('alDateRange')}</label>
          <div className="date-inputs">
            <input type="date" value={filters.startDate} onChange={(e) => updateFilters({ startDate: e.target.value })} />
            <span>{t('alTo')}</span>
            <input type="date" value={filters.endDate} onChange={(e) => updateFilters({ endDate: e.target.value })} />
          </div>
        </div>
        <div className="filter-group">
          <label>{t('user')}</label>
          <select
            value={filters.userId}
            onChange={(e) => {
              const selectedUserId = e.target.value;
              updateFilters({ userId: selectedUserId });
              fetchLogins({ userId: selectedUserId, manual: true, silent: false });
            }}
          >
            <option value="">{t('alAllUsers')}</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
        </div>
        <div className="filter-row">
          <div className="filter-group">
            <label>{t('alColStatus')}</label>
            <select value={filters.status} onChange={(e) => updateFilters({ status: e.target.value })}>
              <option value="">{t('notificationsAll')}</option>
              {statuses.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="filter-group">
            <label>{t('alDevice')}</label>
            <select value={filters.deviceType} onChange={(e) => updateFilters({ deviceType: e.target.value })}>
              <option value="">{t('notificationsAll')}</option>
              {deviceTypes.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="filter-group">
            <label>{t('alColLocation')}</label>
            <input value={filters.location} onChange={(e) => updateFilters({ location: e.target.value })} placeholder={t('alLocationPlaceholder')} />
          </div>
          <button className="btn btn-sm btn-outline" onClick={clearFilters}><RotateCcw size={14} /> {t('searchClear')}</button>
          <button className="btn btn-primary btn-sm" onClick={() => fetchLogins({ manual: true, silent: false })}>{t('alApply')}</button>
        </div>
      </div>

      <div className="bulk-actions" style={{ display: selectedIds.size ? 'flex' : 'none', gap: '0.5rem', marginBottom: '1rem' }}>
        <span>{t('alSelectedCount', { count: selectedIds.size })}</span>
        <button className="btn btn-warning btn-sm" onClick={() => handleBulkAction('archive')}>
          <Archive size={14} /> {t('alArchive')}
        </button>
        <button className="btn btn-success btn-sm" onClick={() => handleBulkAction('restore')}>
          <ArchiveRestore size={14} /> {t('umRestore')}
        </button>
      </div>

      <div className="activity-search">
        <div className="search-wrap">
          <Search size={16} />
          <input value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder={t('alQuickSearch')} />
        </div>
        <div className="activity-search-actions">
          <button className="btn btn-secondary" onClick={handleAutoArchive}><Archive size={16} /> {t('alAutoArchive')}</button>
          {user?.role === 'super_admin' && (
            <button className="btn btn-danger" onClick={handleClearAllLoginHistory}>
              <Archive size={16} /> {t('alClearAllLoginHistory')}
            </button>
          )}
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <Clock3 size={20} />
          <div><div className="stat-value">{filteredRecords.length}</div><div>{t('alEvents')}</div></div>
        </div>
        <div className="stat-card">
          <ShieldCheck size={20} />
          <div><div className="stat-value">{loginCount}</div><div>{t('alLogins')}</div></div>
        </div>
        <div className="stat-card">
          <ShieldCheck size={20} />
          <div><div className="stat-value">{logoutCount}</div><div>{t('alLogouts')}</div></div>
        </div>
        <div className="stat-card">
          <Users size={20} />
          <div><div className="stat-value">{uniqueUsersCount}</div><div>{t('alUsers')}</div></div>
        </div>
      </div>

      {error && <div className="alert-error">{error}</div>}

      {loading ? (
        <div className="loading-card">{t('alLoading')}</div>
      ) : (
        <div className="table-container">
          <table className="table activity-table">
            <thead>
              <tr>
                <th><input type="checkbox" checked={selectedIds.size === filteredRecords.length && filteredRecords.length > 0} onChange={toggleSelectAll} /></th>
                <th>{t('alColTimestamp')}</th>
                <th>{t('alColUsername')}</th>
                <th>{t('alColEvent')}</th>
                <th>{t('alColStatus')}</th>
                <th>{t('alColLocation')}</th>
                <th>{t('alColDeviceType')}</th>
                <th>{t('alColBrowserOs')}</th>
                <th>{t('alColDeviceAgent')}</th>
                <th>{t('alColIP')}</th>
                <th>{t('alColArchived')}</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.length ? filteredRecords.map((record, index) => (
                <tr key={record.id || index}>
                  <td><input type="checkbox" checked={selectedIds.has(record.id)} onChange={() => toggleSelect(record.id)} /></td>
                  <td>{formatTimestamp(record.timestamp, t('reportsNA'))}</td>
                  <td>{record.username || t('alUnknown')}</td>
                  <td><span className={eventTagClass(record.action)}>{record.action || t('alUnknown')}</span></td>
                  <td><span className={statusTagClass(resolveLoginStatus(record))}>{resolveLoginStatus(record)}</span></td>
                  <td title={record.city || record.region || ''}>{record.location}</td>
                  <td>{resolveDeviceType(record)}</td>
                  <td>{resolveBrowser(record)} / {resolveOs(record)}</td>
                  <td className="device-cell" title={resolveDeviceLabel(record)}>
                    <span className="device-cell-text">{resolveDeviceLabel(record)}</span>
                  </td>
                  <td className="mono-cell" title={record.user_agent}>{record.ip_address}</td>
                  <td><span className={archivedTagClass(record.archived_at)}>{formatTimestamp(record.archived_at, t('reportsNA'))}</span></td>
                </tr>
              )) : (
                <tr><td colSpan={11} className="empty-state">{t('alNoLogsMatch')} <button className="link" onClick={clearFilters}>{t('searchClear')}</button></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

export default ActivityLogins;
