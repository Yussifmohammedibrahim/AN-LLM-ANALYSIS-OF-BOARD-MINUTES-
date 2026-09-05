import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Download, Eye, FileText, BarChart2, Trash2, X, RefreshCw } from 'lucide-react';
import { ensureArray } from '../utils/safeMap';
import DynamicIcon from './DynamicIcon';
import { notifyError, notifyInfo, notifySuccess, notifyWarning } from '../utils/notify';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { useConfirm } from './ConfirmProvider';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Bar, Doughnut } from 'react-chartjs-2';
import { aiAPI } from '../api/api';
import { SelectionProvider, useSelection } from './selection/SelectionContext';
import BulkActionsBar from './BulkActionsBar';
import EnhancedPresentationModal from './EnhancedPresentationModal';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
);

const TYPE_MAP = {
  summaries: 'summaries',
  sentiment: 'sentiments',
  actions: 'action_items',
  keywords: 'keywords',
  topics: 'topics'
};

const REPORTS_BATCH_JOB_KEY = 'reports_active_batch_job';
const REPORTS_BATCH_POLL_MS = 1500;
const REPORTS_BATCH_MAX_POLLS = 600;
const THEME_REFRESH_EVENT = 'itds:theme-data-refresh';
const THEME_REFRESH_STORAGE_KEY = 'itds_theme_data_refresh';

const previewText = (value, max = 180) => {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trimEnd()}...`;
};

const splitSummaryBullets = (value) => {
  const normalized = String(value || '')
    .replace(/\s+/g, ' ')
    .replace(/\s*-\s*/g, ' ')
    .trim();

  if (!normalized) return [];

  const sentences = normalized
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim().replace(/[.!?]+$/, ''))
    .filter(Boolean);

  const source = sentences.length >= 2 ? sentences : normalized.split(/[,;]\s*/).map((part) => part.trim()).filter(Boolean);
  const selected = source.slice(0, 3);

  if (selected.length >= 2) {
    return selected.map((item) => item.charAt(0).toUpperCase() + item.slice(1));
  }

  const words = normalized.split(' ');
  if (words.length <= 18) {
    return [normalized.charAt(0).toUpperCase() + normalized.slice(1)];
  }

  const chunkSize = Math.ceil(words.length / 3);
  const chunks = [];
  for (let index = 0; index < words.length && chunks.length < 3; index += chunkSize) {
    const chunk = words.slice(index, index + chunkSize).join(' ').trim();
    if (chunk) {
      chunks.push(chunk.charAt(0).toUpperCase() + chunk.slice(1));
    }
  }
  return chunks.length ? chunks : [normalized.charAt(0).toUpperCase() + normalized.slice(1)];
};

const broadcastThemeDataRefresh = () => {
  const payload = { at: Date.now() };
  try {
    window.localStorage.setItem(THEME_REFRESH_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    // ignore storage failures
  }
  window.dispatchEvent(new CustomEvent(THEME_REFRESH_EVENT, { detail: payload }));
};

const SmartTooltipText = ({ text, previewLength = 180 }) => {
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [anchorPoint, setAnchorPoint] = useState(null);
  const [tooltipStyle, setTooltipStyle] = useState({
    top: -9999,
    left: -9999,
    visibility: 'hidden',
  });

  const fullText = String(text || '').replace(/\s+/g, ' ').trim();
  const preview = previewText(fullText, previewLength);

  useLayoutEffect(() => {
    if (!open || !fullText) return undefined;

    const updatePosition = () => {
      const triggerEl = triggerRef.current;
      const tooltipEl = tooltipRef.current;
      if (!triggerEl || !tooltipEl) return;

      const triggerRect = triggerEl.getBoundingClientRect();
      const tooltipRect = tooltipEl.getBoundingClientRect();
      const gap = 12;
      const margin = 8;
      const cursorOffsetX = 18;
      const cursorOffsetY = 20;
      const point = anchorPoint || {
        x: triggerRect.left + triggerRect.width / 2,
        y: triggerRect.top + triggerRect.height / 2,
      };

      const spaceAbove = point.y - margin;
      const spaceBelow = window.innerHeight - point.y - margin;
      const preferTop = spaceAbove >= tooltipRect.height + gap || spaceAbove >= spaceBelow;

      let top = preferTop
        ? point.y - tooltipRect.height - cursorOffsetY
        : point.y + cursorOffsetY;
      let left = point.x + cursorOffsetX;

      if (left + tooltipRect.width + margin > window.innerWidth) {
        left = point.x - tooltipRect.width - cursorOffsetX;
      }

      const maxTop = Math.max(margin, window.innerHeight - tooltipRect.height - margin);
      const maxLeft = Math.max(margin, window.innerWidth - tooltipRect.width - margin);

      top = Math.min(Math.max(top, margin), maxTop);
      left = Math.min(Math.max(left, margin), maxLeft);

      setTooltipStyle({
        top,
        left,
        visibility: 'visible',
      });
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [fullText, open, anchorPoint]);

  const handleMouseEnter = (event) => {
    setAnchorPoint({ x: event.clientX, y: event.clientY });
    setOpen(true);
  };

  const handleMouseMove = (event) => {
    if (!open) return;
    setAnchorPoint({ x: event.clientX, y: event.clientY });
  };

  const handleFocus = () => {
    const triggerEl = triggerRef.current;
    if (triggerEl) {
      const rect = triggerEl.getBoundingClientRect();
      setAnchorPoint({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
    }
    setOpen(true);
  };

  const handleMouseLeave = () => {
    setOpen(false);
    setAnchorPoint(null);
  };

  if (!preview) return null;

  return (
    <>
      <span
        ref={triggerRef}
        className="reports-tooltip-trigger"
        tabIndex={0}
        onMouseEnter={handleMouseEnter}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onFocus={handleFocus}
        onBlur={() => setOpen(false)}
        aria-label={fullText}
      >
        <span className="reports-summary-text">{preview}</span>
      </span>
      {open && typeof document !== 'undefined' && createPortal(
        <div
          ref={tooltipRef}
          className="reports-tooltip-portal"
          style={tooltipStyle}
          role="tooltip"
        >
          {fullText}
        </div>,
        document.body
      )}
    </>
  );
};

function Reports() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { user } = useAuth();
  const confirm = useConfirm();
  const canManageReportDelivery = ['editor', 'admin', 'super_admin'].includes(user?.role);
  
  // Role-based access control: Viewers can access reports UI, but unsupported roles cannot.
  useEffect(() => {
    if (user && !['viewer', 'editor', 'admin', 'super_admin'].includes(user.role)) {
      notifyError('You do not have permission to access Data and Reporting.');
      navigate('/');
    }
  }, [user, navigate]);
  const [activeTab, setActiveTab] = useState('summaries');
  const [rows, setRows] = useState([]);
  const [sentimentRows, setSentimentRows] = useState([]);
  const [actionRows, setActionRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningAnalysis, setRunningAnalysis] = useState(false);
  const [stoppingAnalysis, setStoppingAnalysis] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState('');
  const [analysisCounts, setAnalysisCounts] = useState({ processed: 0, total: 0 });
  const [selectedItem, setSelectedItem] = useState(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [showFloatingAction, setShowFloatingAction] = useState(false);
  const [showEnhancedModal, setShowEnhancedModal] = useState(false);
  const [deletingItem, setDeletingItem] = useState(false);
  const [reportFilters, setReportFilters] = useState({
    query: '',
    dateFrom: '',
    dateTo: '',
    sentiment: 'all',
    theme: 'all',
  });
  const analysisPanelRef = useRef(null);
  const isMountedRef = useRef(true);

  const saveActiveBatchJob = React.useCallback((jobId) => {
    try {
      localStorage.setItem(REPORTS_BATCH_JOB_KEY, JSON.stringify({ jobId, startedAt: Date.now() }));
    } catch (error) {
      console.warn('Unable to persist active batch job:', error);
    }
  }, []);

  const clearActiveBatchJob = React.useCallback(() => {
    try {
      localStorage.removeItem(REPORTS_BATCH_JOB_KEY);
    } catch (error) {
      console.warn('Unable to clear active batch job:', error);
    }
  }, []);

  const getActiveBatchJob = React.useCallback(() => {
    try {
      const raw = localStorage.getItem(REPORTS_BATCH_JOB_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.jobId) return null;
      return parsed;
    } catch {
      return null;
    }
  }, []);

  const tabs = [
    { id: 'summaries', labelKey: 'reportsTabSummaries', iconName: 'FileText' },
    { id: 'sentiment', labelKey: 'reportsTabSentiment', iconName: 'BarChart2' },
    { id: 'actions', labelKey: 'reportsTabActions' },
    { id: 'keywords', labelKey: 'reportsTabKeywords' },
    { id: 'topics', labelKey: 'reportsTabTopics', iconName: 'Tag' }
  ];

  const normalizeConfidence = (raw) => {
    if (raw === null || raw === undefined || raw === '') return null;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return null;
    return parsed;
  };

  const renderConfidence = (rawConfidence) => {
    const value = normalizeConfidence(rawConfidence);
    if (value === null) return t('reportsNA');
    const percent = value <= 1 ? value * 100 : value;
    return `${percent.toFixed(1)}%`;
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom'
      }
    }
  };

  const loadReportData = React.useCallback(async () => {
    setLoading(true);
    try {
      const [mainRes, sentimentRes, actionRes] = await Promise.all([
        aiAPI.generateReport({ type: TYPE_MAP[activeTab] }),
        aiAPI.generateReport({ type: 'sentiments' }),
        aiAPI.generateReport({ type: 'action_items' })
      ]);

      const mainData = ensureArray(mainRes?.data?.data);
      const normalizedMain = mainData.map((item) => ({
        ...item,
        summary: item.summary || item.summary_text || '',
        confidence: normalizeConfidence(item.confidence ?? item.confidence_score),
        keywordsList: Array.isArray(item.keywords)
          ? item.keywords
          : String(item.keywords || '').split(',').map((x) => x.trim()).filter(Boolean),
        name: item.name || item.topic_name || item.theme_name || '',
        segment_count: Number(item.segment_count || 0)
      }));

      let displayRows = normalizedMain;

      if (activeTab === 'sentiment') {
        const grouped = new Map();
        normalizedMain.forEach((row) => {
          const key = row.meeting_id || row.segment_id || row.sentiment_id;
          if (!key) return;

          const bucket = grouped.get(key) || {
            ...row,
            __confidenceValues: [],
            __latestTs: row.created_at ? Date.parse(row.created_at) || 0 : 0,
          };

          const conf = normalizeConfidence(row.confidence);
          if (conf !== null) bucket.__confidenceValues.push(conf);

          const currentTs = row.created_at ? Date.parse(row.created_at) || 0 : 0;
          if (currentTs >= bucket.__latestTs) {
            bucket.sentiment = row.sentiment;
            bucket.created_at = row.created_at;
            bucket.sentiment_id = row.sentiment_id;
            bucket.segment_id = row.segment_id;
            bucket.__latestTs = currentTs;
          }

          grouped.set(key, bucket);
        });

        displayRows = Array.from(grouped.values())
          .map((row) => {
            const values = row.__confidenceValues || [];
            const avg = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : row.confidence;
            return {
              ...row,
              confidence: avg,
            };
          })
          .sort((a, b) => (Date.parse(b.created_at || '') || 0) - (Date.parse(a.created_at || '') || 0));
      }

      if (activeTab === 'summaries') {
        const grouped = new Map();
        normalizedMain.forEach((row) => {
          const key = row.meeting_id || row.segment_id || row.summary_id;
          if (!key) return;

          const bucket = grouped.get(key) || {
            ...row,
            summary_count: 0,
            __summaryParts: [],
            __confidenceValues: [],
            __latestTs: row.created_at ? Date.parse(row.created_at) || 0 : 0,
          };

          bucket.summary_count += 1;
          if (row.summary) bucket.__summaryParts.push(String(row.summary).trim());

          const conf = normalizeConfidence(row.confidence);
          if (conf !== null) bucket.__confidenceValues.push(conf);

          const currentTs = row.created_at ? Date.parse(row.created_at) || 0 : 0;
          if (currentTs >= bucket.__latestTs) {
            bucket.created_at = row.created_at;
            bucket.summary_id = row.summary_id;
            bucket.segment_id = row.segment_id;
            bucket.__latestTs = currentTs;
          }

          grouped.set(key, bucket);
        });

        displayRows = Array.from(grouped.values())
          .map((row) => {
            const values = row.__confidenceValues || [];
            const avg = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : row.confidence;
            const uniqueParts = Array.from(new Set((row.__summaryParts || []).filter(Boolean)));
            return {
              ...row,
              summary: uniqueParts.join(' '),
              confidence: avg,
            };
          })
          .sort((a, b) => (Date.parse(b.created_at || '') || 0) - (Date.parse(a.created_at || '') || 0));
      }

      if (activeTab === 'keywords') {
        const grouped = new Map();
        normalizedMain.forEach((row) => {
          const key = row.meeting_id || row.segment_id || row.keyword_id;
          if (!key) return;

          const bucket = grouped.get(key) || {
            ...row,
            __confidenceValues: [],
            __keywordSet: new Set(),
            __latestTs: row.created_at ? Date.parse(row.created_at) || 0 : 0,
          };

          String(row.keywords || '')
            .split(',')
            .map((k) => k.trim())
            .filter(Boolean)
            .forEach((k) => bucket.__keywordSet.add(k));

          const conf = normalizeConfidence(row.confidence);
          if (conf !== null) bucket.__confidenceValues.push(conf);

          const currentTs = row.created_at ? Date.parse(row.created_at) || 0 : 0;
          if (currentTs >= bucket.__latestTs) {
            bucket.created_at = row.created_at;
            bucket.keyword_id = row.keyword_id;
            bucket.segment_id = row.segment_id;
            bucket.__latestTs = currentTs;
          }

          grouped.set(key, bucket);
        });

        displayRows = Array.from(grouped.values())
          .map((row) => {
            const values = row.__confidenceValues || [];
            const avg = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : row.confidence;
            return {
              ...row,
              keywords: Array.from(row.__keywordSet || []).join(', '),
              confidence: avg,
            };
          })
          .sort((a, b) => (Date.parse(b.created_at || '') || 0) - (Date.parse(a.created_at || '') || 0));
      }

      if (activeTab === 'topics') {
        const grouped = new Map();
        normalizedMain.forEach((row) => {
          const topicName = String(row.name || '').trim();
          if (!topicName) return;
          const key = topicName.toLowerCase();

          const bucket = grouped.get(key) || {
            ...row,
            name: topicName,
            topic_occurrences: 0,
            __confidenceValues: [],
            __latestTs: row.created_at ? Date.parse(row.created_at) || 0 : 0,
          };

          bucket.topic_occurrences += 1;

          const conf = normalizeConfidence(row.confidence);
          if (conf !== null) bucket.__confidenceValues.push(conf);

          const currentTs = row.created_at ? Date.parse(row.created_at) || 0 : 0;
          if (currentTs >= bucket.__latestTs) {
            bucket.created_at = row.created_at;
            bucket.topic_id = row.topic_id;
            bucket.__latestTs = currentTs;
          }

          grouped.set(key, bucket);
        });

        displayRows = Array.from(grouped.values())
          .map((row) => {
            const values = row.__confidenceValues || [];
            const avg = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : row.confidence;
            return {
              ...row,
              confidence: avg,
            };
          })
          .sort((a, b) => Number(b.topic_occurrences || 0) - Number(a.topic_occurrences || 0));
      }

      setRows(displayRows);
      setSentimentRows(ensureArray(sentimentRes?.data?.data));
      setActionRows(ensureArray(actionRes?.data?.data));
    } catch (error) {
      console.error('Error loading report data:', error);
      notifyError(t('reportsFailedLoad'));
      setRows([]);
      setSentimentRows([]);
      setActionRows([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, t]);

  useEffect(() => {
    loadReportData();
  }, [loadReportData]);

// --- Selection helpers for Reports ---
const SelectAllCheckbox = ({ results = [], getId }) => {
  const { selected, selectAll, clear } = useSelection();
  const allIds = results.map((r, i) => getId(r, i));
  const allSelected = allIds.length > 0 && allIds.every(id => selected.has(id));
  const someSelected = allIds.some(id => selected.has(id));
  const onChange = (e) => e.target.checked ? selectAll(allIds) : clear();
  return (
    <input type="checkbox" aria-label="Select all reports" checked={allSelected} ref={(el) => { if (el) el.indeterminate = !allSelected && someSelected; }} onChange={onChange} />
  );
};

const ReportRow = ({ item, index, activeTab, openPreview, getId }) => {
  const id = getId(item, index);
  const { selected, toggle } = useSelection();
  const isSelected = selected.has(id);
  return (
    <tr tabIndex={0} className={isSelected ? 'row-selected' : ''} aria-selected={isSelected}>
      <td>
        <input type="checkbox" aria-label={`Select row ${index+1}`} checked={isSelected} onChange={() => toggle(id)} onClick={(e) => e.stopPropagation()} />
      </td>
      <td>#{index + 1}</td>
      {activeTab === 'summaries' && (
        <td className="reports-summary-cell">{item.summary ? <SmartTooltipText text={item.summary} previewLength={190} /> : '-'}</td>
      )}
      {activeTab === 'sentiment' && (
        <td className="reports-summary-cell">{item.sentiment ? <SmartTooltipText text={String(item.sentiment).toUpperCase()} previewLength={120} /> : '-'}</td>
      )}
      {activeTab === 'actions' && (
        <td className="reports-summary-cell">{item.item_text ? <SmartTooltipText text={item.item_text} previewLength={170} /> : '-'}</td>
      )}
      {activeTab === 'keywords' && (
        <td className="reports-summary-cell">{item.keywords ? <SmartTooltipText text={item.keywords} previewLength={170} /> : '-'}</td>
      )}
      {activeTab === 'topics' && <td style={{ maxWidth: '420px' }}>{item.name || '-'}</td>}
      {activeTab === 'topics' && <td>{Number(item.topic_occurrences || 1)}</td>}
      <td>{renderConfidence(item.confidence)}</td>
      <td>
        <div className="button-group" style={{ justifyContent: 'flex-start' }}>
          <button className="btn btn-ghost btn-sm" onClick={() => openPreview(item)} title={t('reportsPreviewTitle')} aria-label={t('reportsPreviewTitle')}>
            <Eye size={16} />
          </button>
        </div>
      </td>
    </tr>
  );
};

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const sentimentChartData = useMemo(() => {
    const counts = sentimentRows.reduce((acc, row) => {
      const sentiment = String(row.sentiment || '').toLowerCase();
      if (sentiment === 'positive') acc.positive += 1;
      else if (sentiment === 'negative') acc.negative += 1;
      else acc.neutral += 1;
      return acc;
    }, { positive: 0, neutral: 0, negative: 0 });

    return {
      labels: [t('reportsSentimentPositive'), t('reportsSentimentNeutral'), t('reportsSentimentNegative')],
      datasets: [{
        data: [counts.positive, counts.neutral, counts.negative],
        backgroundColor: ['#22c55e', '#64748b', '#ef4444'],
        borderWidth: 0
      }]
    };
  }, [sentimentRows, t]);

  const actionItemsChartData = useMemo(() => {
    const classifyActionStatus = (row) => {
      const statusSignal = [
        row?.status,
        row?.action_status,
        row?.item_status,
        row?.state,
      ]
        .map((v) => String(v || '').trim().toLowerCase())
        .find(Boolean);

      const textSignal = [
        row?.item_type,
        row?.item_text,
        row?.context,
      ]
        .map((v) => String(v || '').trim().toLowerCase())
        .filter(Boolean)
        .join(' ');

      const source = statusSignal || textSignal;

      const has = (re) => re.test(source);

      if (has(/\b(done|completed?|closed?|resolved?|finished?)\b/)) return 'completed';
      if (has(/\b(blocked|stuck|on[\s-]?hold|deferred?)\b/)) return 'blocked';
      if (has(/\b(in[\s-]?progress|ongoing|doing|active|wip|working)\b/)) return 'inProgress';
      if (has(/\b(open|todo|to[\s-]?do|pending|queued?|backlog|new)\b/)) return 'pending';

      // Fallback for unknown strings: keep visible as unclassified for data quality auditing.
      return 'unclassified';
    };

    const counts = actionRows.reduce((acc, row) => {
      const bucket = classifyActionStatus(row);
      acc[bucket] += 1;
      return acc;
    }, { completed: 0, inProgress: 0, pending: 0, blocked: 0, unclassified: 0 });

    return {
      labels: [t('reportsActionCompleted'), t('reportsActionInProgress'), t('reportsActionPending'), 'Blocked', 'Unclassified'],
      datasets: [{
        label: t('reportsActionStatus'),
        data: [counts.completed, counts.inProgress, counts.pending, counts.blocked, counts.unclassified],
        backgroundColor: ['#22c55e', '#f59e0b', '#ef4444', '#6d28d9', '#64748b'],
        borderWidth: 0
      }]
    };
  }, [actionRows, t]);

  const hasChartData = (chart) => {
    if (!chart || !Array.isArray(chart.datasets)) return false;
    return chart.datasets.some((ds) => Array.isArray(ds.data) && ds.data.some((v) => Number(v) > 0));
  };

  const pollBatchStatus = React.useCallback(async (jobId, maxPolls = REPORTS_BATCH_MAX_POLLS) => {
    let pollCount = 0;
    let finalStatus = null;

    while (pollCount < maxPolls) {
      pollCount += 1;
      const statusResponse = await aiAPI.getBatchAnalysisStatus(jobId);
      const status = statusResponse?.data || {};
      finalStatus = status;

      const processedSoFar = Number(status.processed_meetings || 0);
      const totalMeetings = Number(status.total_meetings || 0);
      const step = status.current_step || t('reportsRunning');

      if (isMountedRef.current) {
        setAnalysisCounts({ processed: processedSoFar, total: totalMeetings });
        setAnalysisProgress(t('reportsStepMeetings', { step, processed: processedSoFar, total: totalMeetings }));
      }

      if (status.status === 'completed') {
        clearActiveBatchJob();
        return status;
      }

      if (status.status === 'canceled') {
        clearActiveBatchJob();
        return status;
      }

      if (status.status === 'failed') {
        clearActiveBatchJob();
        throw new Error(status.error || t('reportsBatchFailedWorker'));
      }

      await new Promise((resolve) => setTimeout(resolve, REPORTS_BATCH_POLL_MS));
    }

    if (!finalStatus || finalStatus.status !== 'completed') {
      throw new Error(t('reportsBatchTimeout'));
    }

    clearActiveBatchJob();
    return finalStatus;
  }, [clearActiveBatchJob, t]);

  const progressPercent = useMemo(() => {
    const total = Number(analysisCounts.total || 0);
    const processed = Number(analysisCounts.processed || 0);
    if (total <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((processed / total) * 100)));
  }, [analysisCounts]);

  const exportReport = async () => {
    try {
      const response = await aiAPI.generateReport({ type: TYPE_MAP[activeTab], format: 'pdf' });
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${activeTab}_${new Date().toISOString().split('T')[0]}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      notifyError(t('reportsFailedExport'));
    }
  };

  const startBatchAnalysisJob = async ({
    payload,
    startingMessage,
    successMessage,
    progressMessage,
    noMeetingsMessage,
  }) => {
    if (!canManageReportDelivery) {
      notifyError('Viewer role is read-only for analysis.');
      return;
    }
    setRunningAnalysis(true);
    setAnalysisProgress(startingMessage);
    setAnalysisCounts({ processed: 0, total: 0 });
    try {
      const startResponse = await aiAPI.startBatchAnalysis(payload);
      const jobId = startResponse?.data?.job_id;
      if (!jobId) {
        throw new Error(t('reportsNoJobId'));
      }

      saveActiveBatchJob(jobId);
      const finalStatus = await pollBatchStatus(jobId);

      if (String(finalStatus?.status || '').toLowerCase() === 'canceled') {
        notifyInfo('Analysis stopped.');
        setAnalysisProgress('Analysis stopped by user.');
        return;
      }

      const processed = Number(finalStatus?.processed_meetings || 0);
      const total = Number(finalStatus?.total_meetings || processed || 0);
      setAnalysisCounts({ processed, total });
      if (processed === 0) {
        notifyInfo(noMeetingsMessage || t('reportsNoMeetingsInfo'));
        setAnalysisProgress(t('reportsNoMeetingsStatus'));
        return;
      }

      const loaderErrors = Array.isArray(finalStatus.loader_errors) ? finalStatus.loader_errors : [];
      if (loaderErrors.length > 0) {
        notifyInfo(t('reportsBatchWarnings', { warning: loaderErrors[0] }));
      }

      notifySuccess(successMessage || t('reportsBatchCompleted', { processed }));
      setAnalysisProgress(progressMessage || t('reportsBatchRefreshing'));
      await loadReportData();
      broadcastThemeDataRefresh();
    } catch (error) {
      clearActiveBatchJob();
      notifyError(t('reportsAnalysisFailed'));
      setAnalysisProgress(t('reportsFailedStatus', { message: error?.message || t('reportsUnknownError') }));
    } finally {
      if (isMountedRef.current) {
        setRunningAnalysis(false);
      }
    }
  };

  const runAnalysis = async () => {
    await startBatchAnalysisJob({
      payload: { 
        reset_existing: true,
        include_themes: true 
      },
      startingMessage: t('reportsStartingBatch'),
    });
  };

  const regenerateThemesAndSummaries = async () => {
    await startBatchAnalysisJob({
      payload: {
        reset_existing: true,
        include_summaries: true,
        include_topics: true,
        include_sentiments: true,
        include_action_items: true,
        include_keywords: true,
        include_themes: true,
      },
      startingMessage: 'Regenerating report analytics...',
      successMessage: 'Report analytics refreshed.',
      progressMessage: 'Report analytics refreshed. Refreshing report data...',
    });
  };

  useEffect(() => {
    const activeJob = getActiveBatchJob();
    if (!activeJob?.jobId) return undefined;

    let cancelled = false;

    const resumeBatchAnalysis = async () => {
      if (cancelled) return;

      setRunningAnalysis(true);
      setAnalysisProgress('Reconnecting to running AI analysis...');

      try {
        const finalStatus = await pollBatchStatus(activeJob.jobId);
        if (cancelled || !isMountedRef.current) return;

        if (String(finalStatus?.status || '').toLowerCase() === 'canceled') {
          setAnalysisProgress('Analysis stopped by user.');
          return;
        }

        const processed = Number(finalStatus?.processed_meetings || 0);
        const total = Number(finalStatus?.total_meetings || processed || 0);
        setAnalysisCounts({ processed, total });

        const loaderErrors = Array.isArray(finalStatus.loader_errors) ? finalStatus.loader_errors : [];
        if (loaderErrors.length > 0) {
          notifyInfo(t('reportsBatchWarnings', { warning: loaderErrors[0] }));
        }

        if (processed > 0) {
          notifySuccess(t('reportsBatchCompleted', { processed }));
        }

        setAnalysisProgress(t('reportsBatchRefreshing'));
        await loadReportData();
      } catch (error) {
        clearActiveBatchJob();
        if (cancelled || !isMountedRef.current) return;
        if (error?.response?.status === 404) {
          setAnalysisProgress('No active analysis job found.');
        } else {
          setAnalysisProgress(t('reportsFailedStatus', { message: error?.message || t('reportsUnknownError') }));
        }
      } finally {
        if (!cancelled && isMountedRef.current) {
          setRunningAnalysis(false);
        }
      }
    };

    resumeBatchAnalysis();

    return () => {
      cancelled = true;
    };
  }, [clearActiveBatchJob, getActiveBatchJob, loadReportData, pollBatchStatus, t]);

  const stopAnalysis = async () => {
    const activeJob = getActiveBatchJob();
    if (!activeJob?.jobId) {
      setRunningAnalysis(false);
      setAnalysisProgress('No running analysis found.');
      return;
    }

    setStoppingAnalysis(true);
    try {
      await aiAPI.cancelBatchAnalysis(activeJob.jobId);
      notifyInfo('Stop request sent. Waiting for analysis to halt...');
      setAnalysisProgress('Stopping analysis...');
    } catch (error) {
      notifyError(error?.response?.data?.error || 'Failed to stop analysis.');
    } finally {
      if (isMountedRef.current) {
        setStoppingAnalysis(false);
      }
    }
  };

  const openPreview = (item) => {
    setSelectedItem(item || null);
    setShowPreviewModal(true);
  };

  const closePreview = () => {
    setShowPreviewModal(false);
    setSelectedItem(null);
  };

  const deleteSelectedMinuteAndAnalysis = async (item) => {
    if (deletingItem) return;

    const targetItem = item || selectedItem;
    if (!targetItem) return;

    const sentimentId = targetItem.sentiment_id;
    const keywordId = targetItem.keyword_id;
    const transcriptId = targetItem.transcript_id;
    const meetingId = targetItem.meeting_id;
    if (!sentimentId && !keywordId && !transcriptId && !meetingId) {
      notifyError(t('reportsDeleteNoId'));
      return;
    }

    let confirmMessage = t('reportsDeleteConfirmMinute');
    if (sentimentId) {
      confirmMessage = t('reportsDeleteConfirmSentiment');
    } else if (keywordId) {
      confirmMessage = t('reportsDeleteConfirmKeyword');
    }

    const result = await confirm({
      title: t('reportsDeletePlusAnalysis'),
      message: confirmMessage,
      actions: [{ label: t('delete'), value: 'delete', variant: 'danger' }],
      cancelLabel: t('cancel'),
    });
    if (result.action !== 'delete') return;

    try {
      setDeletingItem(true);
      if (sentimentId) {
        await aiAPI.deleteSentimentRecord(sentimentId);
        notifySuccess(t('reportsDeletedSentiment'));
      } else if (keywordId) {
        await aiAPI.deleteKeywordRecord(keywordId);
        notifySuccess(t('reportsDeletedKeyword'));
      } else if (transcriptId) {
        await aiAPI.clearTranscriptAnalysis(transcriptId);
        await aiAPI.deleteTranscript(transcriptId);
        notifySuccess(t('reportsDeletedMinuteAnalysis'));
      } else {
        await aiAPI.clearMeetingMinuteAndAnalysis(meetingId);
        notifySuccess(t('reportsDeletedMinuteAnalysis'));
      }

      closePreview();
      await loadReportData();
    } catch (error) {
      if (error?.response?.status === 404) {
        notifyWarning(t('reportsRowMissing'));
        closePreview();
        await loadReportData();
        return;
      }
      console.error('Delete minute + analysis failed:', error);
      notifyError(error?.response?.data?.error || t('reportsDeleteFailed'));
    } finally {
      setDeletingItem(false);
    }
  };

  useEffect(() => {
    if (!showPreviewModal) return undefined;
    const handleEscape = (event) => {
      if (event.key === 'Escape') closePreview();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showPreviewModal]);

  useEffect(() => {
    const panel = analysisPanelRef.current;
    if (!panel) return undefined;

    if (typeof IntersectionObserver === 'undefined') {
      const onScroll = () => {
        const rect = panel.getBoundingClientRect();
        setShowFloatingAction(rect.bottom < 0);
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
      return () => window.removeEventListener('scroll', onScroll);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setShowFloatingAction(!entry.isIntersecting);
      },
      {
        threshold: 0.15,
        rootMargin: '0px 0px -72px 0px',
      }
    );

    observer.observe(panel);

    return () => observer.disconnect();
  }, []);

  const previewRows = rows;

  const reportThemes = useMemo(() => {
    return Array.from(new Set(previewRows.map((row) => String(row.name || row.topic_name || '').trim()).filter(Boolean))).slice(0, 50);
  }, [previewRows]);

  const filteredPreviewRows = useMemo(() => {
    const query = reportFilters.query.trim().toLowerCase();
    const fromTs = reportFilters.dateFrom ? Date.parse(reportFilters.dateFrom) : null;
    const toTs = reportFilters.dateTo ? Date.parse(`${reportFilters.dateTo}T23:59:59`) : null;

    return previewRows.filter((row) => {
      const rowText = [row.summary, row.sentiment, row.item_text, row.keywords, row.name, row.topic_name, row.theme_name]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase())
        .join(' ');
      if (query && !rowText.includes(query)) return false;

      const rowTs = Date.parse(row.created_at || row.updated_at || row.meeting_date || '') || null;
      if (fromTs && rowTs && rowTs < fromTs) return false;
      if (toTs && rowTs && rowTs > toTs) return false;

      if (reportFilters.sentiment !== 'all') {
        const rowSentiment = String(row.sentiment || '').trim().toLowerCase();
        if (rowSentiment !== reportFilters.sentiment) return false;
      }

      if (reportFilters.theme !== 'all') {
        const rowTheme = String(row.name || row.topic_name || row.theme_name || '').trim().toLowerCase();
        if (rowTheme !== reportFilters.theme.toLowerCase()) return false;
      }

      return true;
    });
  }, [previewRows, reportFilters]);

  const clearReportFilters = () => {
    setReportFilters({ query: '', dateFrom: '', dateTo: '', sentiment: 'all', theme: 'all' });
  };

  return (
    <div className="dashboard">
      <div className="page-header flex justify-between items-center">
        <div>
          <h1 className="page-title">{t('reportsTitle')}</h1>
          <p className="page-subtitle">{t('reportsSubtitle')}</p>
        </div>
        <div className="button-group">
          {canManageReportDelivery && (
            <button className="btn btn-outline" onClick={() => navigate('/reports/schedules')}>
              View Schedules
            </button>
          )}
          {canManageReportDelivery && (
            <button className="btn btn-secondary" onClick={() => navigate('/settings#report-schedule-settings')}>
              Schedule Delivery
            </button>
          )}
          <button className="btn btn-primary" onClick={exportReport}>
            <Download size={18} />
            Export PDF
          </button>
          <button className="btn btn-secondary" onClick={() => setShowEnhancedModal(true)} title="Advanced presentation export with branding, analytics, and scheduling">
            ✨ Advanced Export (Beta)
          </button>
        </div>
      </div>

      <div className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.iconName && <DynamicIcon name={tab.iconName} size={18} style={{ marginRight: '0.5rem', display: 'inline' }} />}
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      <div className="card reports-analysis-panel mb-4" ref={analysisPanelRef}>
        <div className="card-body text-center">
          <h3 className="font-semibold mb-2">{t('reportsRunAI')}</h3>
          <p className="text-secondary text-sm mb-4">{t('reportsGenerateFor', { tab: t(tabs.find((tab) => tab.id === activeTab)?.labelKey || 'reportsTabSummaries') })}</p>
          <div className="reports-analysis-cta">
            {/* Tooltip wrapper: use title on span so disabled button still shows explanation */}
            <span title={!canManageReportDelivery ? 'Viewer role is read-only for analysis.' : ''} style={{ display: 'inline-block' }}>
              <button className="btn btn-primary" onClick={runAnalysis} disabled={runningAnalysis || !canManageReportDelivery} title="Re-run AI analysis and purge existing noise">
                <BarChart2 size={18} />
                {runningAnalysis ? t('reportsRunning') : 'Run Full Analysis'}
              </button>
            </span>
            <span title={!canManageReportDelivery ? 'Viewer role is read-only for analysis.' : ''} style={{ display: 'inline-block' }}>
              <button className="btn btn-outline" onClick={regenerateThemesAndSummaries} disabled={runningAnalysis || !canManageReportDelivery} title="Purge bad data and regenerate all themes and summaries">
                <RefreshCw size={18} className={runningAnalysis ? 'animate-spin' : ''} />
                Regenerate AI Data
              </button>
            </span>
            {runningAnalysis && (
              <button className="btn btn-outline" onClick={stopAnalysis} disabled={stoppingAnalysis}>
                <X size={18} />
                {stoppingAnalysis ? 'Stopping...' : 'Stop Analysis'}
              </button>
            )}
          </div>
          {(runningAnalysis || analysisCounts.total > 0) && (
            <div className="reports-analysis-progress">
              <div className="flex justify-between mb-1 reports-analysis-progress-meta">
                <span>{t('reportsProgress')}</span>
                <span>{progressPercent}%</span>
              </div>
              <div className="progress reports-analysis-progress-track">
                <div className="progress-bar" style={{ width: `${progressPercent}%`, background: 'var(--primary)' }}></div>
              </div>
            </div>
          )}
          {analysisProgress && (
            <p className="text-secondary text-sm mt-3 reports-analysis-status">
              {analysisProgress}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-2 mb-4">
        <div className="chart-container">
          <div className="chart-header">
            <h3 className="chart-title">{t('reportsSentimentOverview')}</h3>
          </div>
          <div style={{ height: '250px', padding: '1rem' }}>
            {hasChartData(sentimentChartData)
              ? <Doughnut data={sentimentChartData} options={chartOptions} />
              : <div className="no-data">{t('reportsNoSentimentRecords')}</div>}
          </div>
        </div>

        <div className="chart-container">
          <div className="chart-header">
            <h3 className="chart-title">{t('reportsActionStatus')}</h3>
          </div>
          <div style={{ height: '250px', padding: '1rem' }}>
            {hasChartData(actionItemsChartData)
              ? <Bar data={actionItemsChartData} options={chartOptions} />
              : <div className="no-data">{t('reportsNoActionRecords')}</div>}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            {t('reportsTabReport', { tab: t(tabs.find((tab) => tab.id === activeTab)?.labelKey || 'reportsTabSummaries') })}
            <span style={{ marginLeft: '0.5rem', color: '#64748b', fontSize: '0.9rem', fontWeight: 600 }}>
              ({previewRows.length} rows)
            </span>
          </h3>
        </div>
        <div className="card-body">
          <div className="card mb-3" style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
            <div className="card-body">
              <div className="grid grid-2" style={{ gap: '0.75rem' }}>
                <input className="form-input" value={reportFilters.query} onChange={(e) => setReportFilters((prev) => ({ ...prev, query: e.target.value }))} placeholder="Filter by date, theme, sentiment, keyword..." />
                <select className="form-select" value={reportFilters.theme} onChange={(e) => setReportFilters((prev) => ({ ...prev, theme: e.target.value }))}>
                  <option value="all">All themes</option>
                  {reportThemes.map((theme) => <option key={theme} value={theme}>{theme}</option>)}
                </select>
                <select className="form-select" value={reportFilters.sentiment} onChange={(e) => setReportFilters((prev) => ({ ...prev, sentiment: e.target.value }))}>
                  <option value="all">All sentiment</option>
                  <option value="positive">Positive</option>
                  <option value="neutral">Neutral</option>
                  <option value="negative">Negative</option>
                </select>
                <div className="flex gap-2">
                  <input className="form-input" type="date" value={reportFilters.dateFrom} onChange={(e) => setReportFilters((prev) => ({ ...prev, dateFrom: e.target.value }))} />
                  <input className="form-input" type="date" value={reportFilters.dateTo} onChange={(e) => setReportFilters((prev) => ({ ...prev, dateTo: e.target.value }))} />
                </div>
              </div>
              <div className="flex items-center justify-between mt-3" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
                <p className="text-xs text-secondary" style={{ margin: 0 }}>Showing {filteredPreviewRows.length} of {previewRows.length} rows</p>
                <button className="btn btn-outline btn-sm" onClick={clearReportFilters}>Clear filters</button>
              </div>
            </div>
          </div>
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : filteredPreviewRows.length === 0 ? (
            <div className="empty-state">
              <FileText size={48} className="empty-icon" />
              <h3 className="empty-title">{t('reportsNoData')}</h3>
              <p>{previewRows.length === 0 ? t('reportsNoBackendRecords') : 'No rows match the current filters.'}</p>
            </div>
          ) : (
            <div className="table-container reports-table-container">
              <SelectionProvider>
                <BulkActionsBar activeTab={activeTab} itemsMap={filteredPreviewRows.reduce((acc, r, i) => { const key = r.summary_id || r.sentiment_id || r.keyword_id || r.topic_id || r.meeting_id || `r${i}`; acc[key] = r; return acc; }, {})} onDeleteComplete={loadReportData} />
                <table className="table">
                  <thead>
                  <tr>
                    <th>
                      <SelectAllCheckbox results={filteredPreviewRows} getId={(r,i)=> r.summary_id || r.sentiment_id || r.keyword_id || r.topic_id || r.meeting_id || `r${i}`} />
                    </th>
                    <th>{t('reportsColID')}</th>
                    {activeTab === 'summaries' && <th>{t('reportsColSummary')}</th>}
                    {activeTab === 'sentiment' && <th>{t('reportsColSentiment')}</th>}
                    {activeTab === 'actions' && <th>{t('reportsColAction')}</th>}
                    {activeTab === 'keywords' && <th>{t('reportsColKeywords')}</th>}
                    {activeTab === 'topics' && <th>{t('reportsColTopic')}</th>}
                    {activeTab === 'topics' && <th>{t('reportsColOccurrences')}</th>}
                    <th>{t('reportsColConfidence')}</th>
                    <th>{t('reportsColActions')}</th>
                  </tr>
                </thead>
                  <tbody>
                    {filteredPreviewRows.map((item, index) => (
                      <ReportRow
                        key={item.summary_id || item.sentiment_id || item.keyword_id || item.topic_id || item.meeting_id || index}
                        item={item}
                        index={index}
                        activeTab={activeTab}
                        openPreview={openPreview}
                        getId={(r, i) => r.summary_id || r.sentiment_id || r.keyword_id || r.topic_id || r.meeting_id || `r${i}`}
                      />
                    ))}
                  </tbody>
                </table>
              </SelectionProvider>
            </div>
          )}
        </div>
      </div>

      {showPreviewModal && selectedItem && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) closePreview(); }}>
          <div className="modal report-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">{t('reportsPreviewTitle')}</h3>
              <button className="modal-close" onClick={closePreview} aria-label={t('reportsPreviewCloseAria')}>
                <X size={18} />
              </button>
            </div>
            <div className="modal-body report-preview-body">
              {selectedItem && (selectedItem.sentiment_id || selectedItem.keyword_id || selectedItem.transcript_id || selectedItem.meeting_id) && (
                <div className="card" style={{ marginBottom: '1rem', border: '1px solid #fecaca', background: '#fff1f2' }}>
                  <div className="card-body" style={{ padding: '0.9rem 1rem' }}>
                    <div className="flex justify-between items-center" style={{ gap: '1rem', flexWrap: 'wrap' }}>
                      <div>
                        <h4 className="font-semibold" style={{ marginBottom: '0.25rem' }}>{t('reportsMinuteActions')}</h4>
                        <p className="text-sm text-secondary" style={{ margin: 0 }}>
                          {selectedItem.sentiment_id
                            ? t('reportsDeleteOnlySentiment')
                            : selectedItem.keyword_id
                              ? t('reportsDeleteOnlyKeyword')
                              : t('reportsDeleteMinuteAndAnalysis')}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-danger"
                        disabled={deletingItem}
                        onClick={() => deleteSelectedMinuteAndAnalysis(selectedItem)}
                      >
                        <Trash2 size={16} />
                        {deletingItem
                          ? t('reportsDeleting')
                          : selectedItem.sentiment_id
                            ? t('reportsDeleteSentiment')
                            : selectedItem.keyword_id
                              ? t('reportsDeleteKeyword')
                              : t('reportsDeletePlusAnalysis')}
                      </button>
                    </div>
                  </div>
                </div>
              )}
              {Object.entries(selectedItem).map(([k, v]) => {
                const isSummaryField = activeTab === 'summaries' && ['summary', 'summary_text'].includes(k);

                return (
                  <div className="form-group" key={k}>
                    <label className="form-label">{k}</label>
                    {isSummaryField ? (
                      <ul className="report-summary-bullets">
                        {splitSummaryBullets(v).map((bullet, index) => (
                          <li key={`${k}-${index}`}>{bullet}</li>
                        ))}
                      </ul>
                    ) : (
                      <div className="report-preview-value">{Array.isArray(v) ? v.join(', ') : String(v)}</div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-primary" onClick={closePreview}>{t('close')}</button>
            </div>
          </div>
        </div>
      )}

      {showFloatingAction && !showPreviewModal && (
        <button
          className="btn btn-primary reports-fab"
          onClick={runAnalysis}
          disabled={runningAnalysis}
          aria-label={t('reportsRunAI')}
          title={t('reportsRunAI')}
        >
          <BarChart2 size={18} />
          <span>{runningAnalysis ? t('reportsRunning') : t('reportsRunAnalysis')}</span>
        </button>
      )}

      {/* Enhanced Presentation Modal */}
      {showEnhancedModal && (
        <EnhancedPresentationModal
          year={new Date().getFullYear()}
          onClose={() => setShowEnhancedModal(false)}
        />
      )}
    </div>
  );
}

export default Reports;
