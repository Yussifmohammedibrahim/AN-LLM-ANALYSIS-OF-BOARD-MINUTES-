import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, Download, Edit3, FlaskConical, Mail, Plus, SendHorizontal, Save, Sparkles, Trash2, Clock3, Users } from 'lucide-react';
import { eventsAPI, aiAPI } from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';
import { useConfirm } from './ConfirmProvider';
import './EventsHub.css';

const ROLE_OPTIONS = ['viewer', 'editor', 'admin', 'super_admin'];

const initialForm = {
  title: '',
  description: '',
  templateName: 'meeting_notice',
  meetingId: '',
  meetingDate: '',
  startTime: '',
  endTime: '',
  location: '',
  meetingLink: '',
  aiSummary: '',
  audienceRoles: ['viewer', 'editor', 'admin', 'super_admin'],
  onlyEmailOptIn: true,
  showAllUsers: false,
  reminder24h: true,
  reminderDayOf: true,
  reminderPost: false,
  scheduledSendAt: '',
};

const toDatetimeLocalValue = (value) => {
  if (!value) return '';
  const text = String(value).trim();
  if (!text) return '';
  const normalized = text.includes('T') ? text : text.replace(' ', 'T');
  return normalized.slice(0, 16);
};

function EventsHub() {
  const confirm = useConfirm();
  const [form, setForm] = useState(initialForm);
  const [events, setEvents] = useState([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [aiRunning, setAiRunning] = useState(false);
  const [sendingEventId, setSendingEventId] = useState(null);
  const [editingEventId, setEditingEventId] = useState(null);

  const roleText = useMemo(
    () => (form.audienceRoles.length ? form.audienceRoles.join(', ') : 'none'),
    [form.audienceRoles]
  );

  const fetchEvents = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoadingEvents(true);
    }
    try {
      const response = await eventsAPI.listEvents({ limit: 100 });
      setEvents(response.data?.events || []);
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to load events.');
    } finally {
      if (!silent) {
        setLoadingEvents(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const hasActiveScheduledEvents = useMemo(
    () => events.some((item) => {
      const status = String(item?.status || '').toLowerCase();
      if (status === 'scheduled' || status === 'sending') {
        return true;
      }

      const scheduled = item?.scheduled_send_at || item?.scheduledSendAt;
      if (!scheduled || status === 'sent' || status === 'failed') {
        return false;
      }

      const scheduledTs = Date.parse(String(scheduled));
      return Number.isFinite(scheduledTs) && scheduledTs <= Date.now() + (15 * 60 * 1000);
    }),
    [events]
  );

  useEffect(() => {
    const intervalMs = hasActiveScheduledEvents ? 5000 : 30000;
    const timer = window.setInterval(() => {
      if (!document.hidden) {
        fetchEvents({ silent: true });
      }
    }, intervalMs);

    return () => window.clearInterval(timer);
  }, [fetchEvents, hasActiveScheduledEvents]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (!document.hidden) {
        fetchEvents({ silent: true });
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [fetchEvents]);

  const resetForm = () => {
    setForm(initialForm);
    setPreview(null);
    setEditingEventId(null);
  };

  const onInputChange = (event) => {
    const { name, value, type, checked } = event.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const onRoleToggle = (role) => {
    setForm((prev) => {
      const hasRole = prev.audienceRoles.includes(role);
      const nextRoles = hasRole
        ? prev.audienceRoles.filter((item) => item !== role)
        : [...prev.audienceRoles, role];
      return { ...prev, audienceRoles: nextRoles };
    });
  };

  const applyReminderPreset = (preset) => {
    if (preset === 'standard') {
      setForm((prev) => ({ ...prev, reminder24h: true, reminderDayOf: true, reminderPost: false }));
      notifySuccess('Applied Standard reminder preset.');
      return;
    }
    if (preset === 'minimal') {
      setForm((prev) => ({ ...prev, reminder24h: false, reminderDayOf: true, reminderPost: false }));
      notifySuccess('Applied Minimal reminder preset.');
      return;
    }
    if (preset === 'full') {
      setForm((prev) => ({ ...prev, reminder24h: true, reminderDayOf: true, reminderPost: true }));
      notifySuccess('Applied Full reminder preset.');
    }
  };

  const applyAudienceFilter = (filterType) => {
    let roles = [];
    if (filterType === 'all') roles = ['viewer', 'editor', 'admin', 'super_admin'];
    else if (filterType === 'editors+') roles = ['editor', 'admin', 'super_admin'];
    else if (filterType === 'admins') roles = ['admin', 'super_admin'];
    else if (filterType === 'admins_only') roles = ['admin'];
    else if (filterType === 'viewers') roles = ['viewer'];
    
    if (roles.length > 0) {
      setForm((prev) => ({ ...prev, audienceRoles: roles }));
      notifySuccess(`Audience filter applied: ${filterType}`);
    }
  };

  const runAIAssist = async () => {
    if (!form.description.trim()) {
      notifyError('Add a meeting description first so AI can generate a summary.');
      return;
    }
    setAiRunning(true);
    try {
      const response = await aiAPI.simplifyText(form.description);
      const aiText = response?.data?.simplified_text || response?.data?.text || response?.data?.result || '';
      if (!aiText) {
        notifyError('AI summary did not return content.');
        return;
      }
      setForm((prev) => ({ ...prev, aiSummary: String(aiText).trim() }));
      notifySuccess('AI summary generated.');
    } catch (error) {
      notifyError(error.response?.data?.error || 'AI summary failed.');
    } finally {
      setAiRunning(false);
    }
  };

  const previewRecipients = async () => {
    if (!form.audienceRoles.length) {
      notifyError('Select at least one audience role.');
      return;
    }
    setPreviewing(true);
    try {
      const response = await eventsAPI.previewRecipients({
        audienceRoles: form.audienceRoles,
        onlyEmailOptIn: form.onlyEmailOptIn,
        showAllUsers: form.showAllUsers || false,
      });
      setPreview(response.data);
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to preview recipients.');
    } finally {
      setPreviewing(false);
    }
  };

  const openForEdit = (event) => {
    setEditingEventId(event.event_id);
    setForm({
      title: event.title || '',
      description: event.description || '',
      templateName: event.template_name || event.templateName || 'meeting_notice',
      meetingId: event.meeting_id || event.meetingId || '',
      meetingDate: event.meeting_date || '',
      startTime: event.start_time || '',
      endTime: event.end_time || '',
      location: event.location || '',
      meetingLink: event.meeting_link || '',
      aiSummary: event.ai_summary || '',
      audienceRoles: Array.isArray(event.audienceRoles) && event.audienceRoles.length ? event.audienceRoles : ROLE_OPTIONS,
      onlyEmailOptIn: Boolean(event.only_email_opt_in ?? event.onlyEmailOptIn ?? true),
      reminder24h: Boolean(event.reminder_24h ?? event.reminder24h ?? true),
      reminderDayOf: Boolean(event.reminder_day_of ?? event.reminderDayOf ?? true),
      reminderPost: Boolean(event.reminder_post ?? event.reminderPost ?? false),
      scheduledSendAt: toDatetimeLocalValue(event.scheduled_send_at || event.scheduledSendAt || ''),
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const buildPayload = () => ({
    title: form.title.trim(),
    description: form.description.trim(),
    templateName: form.templateName,
    meetingId: form.meetingId ? Number(form.meetingId) : null,
    meetingDate: form.meetingDate,
    startTime: form.startTime,
    endTime: form.endTime,
    location: form.location.trim(),
    meetingLink: form.meetingLink.trim(),
    aiSummary: form.aiSummary.trim(),
    audienceRoles: form.audienceRoles,
    onlyEmailOptIn: form.onlyEmailOptIn,
    reminder24h: form.reminder24h,
    reminderDayOf: form.reminderDayOf,
    reminderPost: form.reminderPost,
    scheduledSendAt: form.scheduledSendAt || '',
  });

  const saveEvent = async () => {
    setSaving(true);
    try {
      const payload = buildPayload();
      const response = editingEventId
        ? await eventsAPI.updateEvent(editingEventId, payload)
        : await eventsAPI.createEvent(payload);

      notifySuccess(editingEventId ? 'Event updated.' : `Event saved (ID: ${response.data?.event_id}).`);
      resetForm();
      fetchEvents();
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to save event.');
    } finally {
      setSaving(false);
    }
  };

  const deleteEvent = async (eventId) => {
    const result = await confirm({
      title: 'Delete Event',
      message: 'Delete this event? This will keep audit history but hide it from the list.',
      actions: [{ label: 'Delete', value: 'delete', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'delete') return;
    try {
      await eventsAPI.deleteEvent(eventId);
      notifySuccess('Event deleted.');
      if (editingEventId === eventId) {
        resetForm();
      }
      fetchEvents();
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to delete event.');
    }
  };

  const sendEvent = async (eventId) => {
    setSendingEventId(eventId);
    try {
      const response = await eventsAPI.sendEvent(eventId);
      const sent = response.data?.email?.sent ?? 0;
      const failed = response.data?.email?.failed ?? 0;
      notifySuccess(`Event sent. Success: ${sent}, Failed: ${failed}`);
      fetchEvents();
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to send event notifications.');
    } finally {
      setSendingEventId(null);
    }
  };

  const sendTestEmail = async (eventId) => {
    setSendingEventId(eventId);
    try {
      await eventsAPI.sendTestEmail(eventId);
      notifySuccess('Test email sent to your admin email.');
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to send test email.');
    } finally {
      setSendingEventId(null);
    }
  };

  const downloadCalendar = async (eventId) => {
    try {
      const response = await eventsAPI.downloadCalendar(eventId);
      const blob = new Blob([response.data], { type: 'text/calendar;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `event-${eventId}.ics`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      notifySuccess('Calendar file downloaded.');
    } catch (error) {
      notifyError(error.response?.data?.error || 'Failed to download calendar file.');
    }
  };

  const scheduledLabel = editingEventId ? 'Update Event' : 'Save Event';
  const scheduledHint = form.scheduledSendAt
    ? 'This event will be auto-sent at the scheduled time.'
    : 'Leave blank to keep this event as a draft until you click Send Email.';

  const statusClassName = (status) => {
    const value = String(status || 'draft').toLowerCase();
    if (value === 'sent') return 'events-hub-status events-hub-status-sent';
    if (value === 'scheduled') return 'events-hub-status events-hub-status-scheduled';
    if (value === 'sending') return 'events-hub-status events-hub-status-sending';
    if (value === 'failed') return 'events-hub-status events-hub-status-failed';
    return 'events-hub-status events-hub-status-draft';
  };

  return (
    <div className="page-content events-hub">
      <div className="page-header">
        <h1 className="page-title">Event Center</h1>
        <p className="page-subtitle">
          Create meeting events, edit them later, filter recipients by role, preview recipients, and send immediately or on schedule.
        </p>
      </div>

      <div className="card events-hub-card">
        <h3 className="card-title events-hub-title-row">
          <CalendarDays size={18} /> {editingEventId ? 'Edit Event Notice' : 'Create Event Notice'}
        </h3>

        <div className="grid grid-2 events-hub-grid">
          <div className="form-group">
            <label>Event Title</label>
            <input name="title" value={form.title} onChange={onInputChange} placeholder="Board meeting update" />
          </div>
          <div className="form-group">
            <label>Template</label>
            <select name="templateName" value={form.templateName} onChange={onInputChange}>
              <option value="meeting_notice">Meeting Notice</option>
              <option value="agenda_reminder">Agenda Reminder</option>
              <option value="post_meeting_summary">Post Meeting Summary</option>
            </select>
          </div>
          <div className="form-group">
            <label>Meeting ID (Optional)</label>
            <input name="meetingId" type="number" value={form.meetingId} onChange={onInputChange} placeholder="1024" />
          </div>
          <div className="form-group">
            <label>Meeting Date</label>
            <input type="date" name="meetingDate" value={form.meetingDate} onChange={onInputChange} />
          </div>
          <div className="form-group">
            <label>Start Time</label>
            <input type="time" name="startTime" value={form.startTime} onChange={onInputChange} />
          </div>
          <div className="form-group">
            <label>End Time</label>
            <input type="time" name="endTime" value={form.endTime} onChange={onInputChange} />
          </div>
          <div className="form-group">
            <label>Location</label>
            <input name="location" value={form.location} onChange={onInputChange} placeholder="Main Campus, Board Room A" />
          </div>
          <div className="form-group">
            <label>Meeting Link</label>
            <input name="meetingLink" value={form.meetingLink} onChange={onInputChange} placeholder="https://..." />
          </div>
        </div>

        <div className="form-group events-hub-section-gap">
          <label>Description</label>
          <textarea
            name="description"
            rows={4}
            value={form.description}
            onChange={onInputChange}
            placeholder="Describe key agenda details and necessary instructions."
          />
        </div>

        <div className="form-group events-hub-section-gap">
          <label className="events-hub-inline-label">
            <Sparkles size={16} /> AI Summary
          </label>
          <textarea
            name="aiSummary"
            rows={3}
            value={form.aiSummary}
            onChange={onInputChange}
            placeholder="AI-generated meeting summary appears here."
          />
          <button type="button" className="btn btn-outline btn-sm events-hub-btn-top" onClick={runAIAssist} disabled={aiRunning}>
            {aiRunning ? 'Generating...' : 'Generate AI Summary'}
          </button>
        </div>

        <div className="form-group events-hub-section-gap">
          <div className="events-hub-audience-header">
            <label className="events-hub-inline-label">
              <Users size={16} /> Audience Role Filters
            </label>
            <select className="events-hub-audience-filter" onChange={(e) => applyAudienceFilter(e.target.value)} defaultValue="">
              <option value="">Quick filters</option>
              <option value="all">All Roles</option>
              <option value="editors+">Editors & Up</option>
              <option value="admins">Admins & Up</option>
              <option value="admins_only">Admins Only</option>
              <option value="viewers">Viewers Only</option>
            </select>
          </div>
          <div className="events-hub-role-list">
            {ROLE_OPTIONS.map((role) => (
              <label key={role} className="events-hub-role-item">
                <input
                  type="checkbox"
                  checked={form.audienceRoles.includes(role)}
                  onChange={() => onRoleToggle(role)}
                />
                <span>{role}</span>
              </label>
            ))}
          </div>
          <div className="text-muted events-hub-small-note">Selected roles: {roleText}</div>
        </div>

        <label className="events-hub-inline-check">
          <input
            type="checkbox"
            name="onlyEmailOptIn"
            checked={form.onlyEmailOptIn}
            onChange={onInputChange}
          />
          <span>Send only to users who enabled email alerts</span>
        </label>

        <label className="events-hub-inline-check">
          <input
            type="checkbox"
            name="showAllUsers"
            checked={form.showAllUsers || false}
            onChange={onInputChange}
          />
          <span>Show all users in preview (bypass email preferences)</span>
        </label>

        <div className="events-hub-reminders">
          <div className="events-hub-reminder-tools">
            <select
              onChange={(e) => {
                if (e.target.value !== 'custom') {
                  applyReminderPreset(e.target.value);
                }
                e.target.value = 'custom';
              }}
              defaultValue="custom"
              aria-label="Reminder preset"
            >
              <option value="custom">Reminder presets</option>
              <option value="standard">Standard (24h + Day-Of)</option>
              <option value="minimal">Minimal (Day-Of only)</option>
              <option value="full">Full (All reminders)</option>
            </select>
          </div>

          <label className="events-hub-inline-check">
            <input type="checkbox" name="reminder24h" checked={form.reminder24h} onChange={onInputChange} />
            <span>Send reminder 24 hours before meeting</span>
          </label>
          <label className="events-hub-inline-check">
            <input type="checkbox" name="reminderDayOf" checked={form.reminderDayOf} onChange={onInputChange} />
            <span>Send day-of reminder at 08:00</span>
          </label>
          <label className="events-hub-inline-check">
            <input type="checkbox" name="reminderPost" checked={form.reminderPost} onChange={onInputChange} />
            <span>Send post-meeting follow-up 2 hours after start</span>
          </label>
        </div>

        <div className="form-group events-hub-section-gap">
          <label className="events-hub-inline-label">
            <Clock3 size={16} /> Schedule Send Time
          </label>
          <input
            type="datetime-local"
            name="scheduledSendAt"
            value={form.scheduledSendAt}
            onChange={onInputChange}
          />
          <div className="text-muted events-hub-small-note">{scheduledHint}</div>
        </div>

        <div className="events-hub-actions">
          <button type="button" className="btn btn-outline" onClick={previewRecipients} disabled={previewing}>
            <Users size={16} /> {previewing ? 'Previewing...' : 'Preview Recipients'}
          </button>
          <button type="button" className="btn btn-primary" onClick={saveEvent} disabled={saving}>
            <Save size={16} /> {saving ? 'Saving...' : scheduledLabel}
          </button>
          <button type="button" className="btn btn-outline" onClick={resetForm}>
            <Plus size={16} /> Clear Form
          </button>
        </div>

        {preview && (
          <div className="card events-hub-preview-card">
            <h4 className="card-title events-hub-preview-title">
              <Mail size={16} /> Recipient Preview
            </h4>
            <div className="text-muted events-hub-preview-row">
              Total recipients: <strong>{preview.count || 0}</strong>
            </div>
            <div className="text-muted events-hub-preview-row">
              Role breakdown: {Object.keys(preview.roles || {}).length ? Object.entries(preview.roles).map(([role, count]) => `${role}: ${count}`).join(' | ') : 'none'}
            </div>
            <div className="events-hub-preview-list">
              {(preview.recipients || []).map((user) => (
                <div key={`${user.user_id}-${user.email}`} className="events-hub-preview-item">
                  {user.username} ({user.role}) - {user.email}
                </div>
              ))}
              {(!preview.recipients || preview.recipients.length === 0) && (
                <div className="text-muted">No recipients matched current filters.</div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="card events-hub-card">
        <h3 className="card-title events-hub-title-row">
          <Mail size={18} /> Saved Events
        </h3>
        {loadingEvents ? (
          <div className="text-muted">Loading events...</div>
        ) : events.length === 0 ? (
          <div className="text-muted">No saved events yet.</div>
        ) : (
          <div className="events-hub-table-wrap">
            <table className="activity-table events-hub-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Date</th>
                  <th>Template</th>
                  <th>Status</th>
                  <th>Scheduled For</th>
                  <th>Audience</th>
                  <th>Email Sent</th>
                  <th>Email Failed</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((item) => (
                  <tr key={item.event_id}>
                    <td className="events-hub-cell-title">{item.title}</td>
                    <td className="events-hub-cell-date">{item.meeting_date || 'TBA'}</td>
                    <td>
                      <span className="events-hub-template-chip">{item.template_name || item.templateName || 'meeting_notice'}</span>
                    </td>
                    <td>
                      <span className={statusClassName(item.status)}>{item.status || 'draft'}</span>
                    </td>
                    <td>{item.scheduled_send_at || '—'}</td>
                    <td>{Array.isArray(item.audienceRoles) ? item.audienceRoles.join(', ') : 'n/a'}</td>
                    <td>
                      <span className="events-hub-metric-chip events-hub-metric-chip-success">{item.sent_count || 0}</span>
                    </td>
                    <td>
                      <span className="events-hub-metric-chip events-hub-metric-chip-danger">{item.failed_count || 0}</span>
                    </td>
                    <td>
                      <div className="events-hub-row-actions">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline"
                          onClick={() => openForEdit(item)}
                        >
                          <Edit3 size={14} /> Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-primary"
                          onClick={() => sendEvent(item.event_id)}
                          disabled={sendingEventId === item.event_id}
                        >
                          <SendHorizontal size={14} /> {sendingEventId === item.event_id ? 'Sending...' : 'Send Now'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-outline"
                          onClick={() => sendTestEmail(item.event_id)}
                          disabled={sendingEventId === item.event_id}
                        >
                          <FlaskConical size={14} /> Test
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-outline"
                          onClick={() => downloadCalendar(item.event_id)}
                        >
                          <Download size={14} /> ICS
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => deleteEvent(item.event_id)}
                        >
                          <Trash2 size={14} /> Delete
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
  );
}

export default EventsHub;
