import React, { useContext, useMemo, useCallback, useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import LoadingSpinner from './LoadingSpinner';
import CardState from './CardState';
import {
  FileText, BarChart2,
  TrendingUp, CheckCircle, Radio, Download, ChevronDown, CalendarPlus, Presentation
} from 'lucide-react';
import { aiAPI } from '../api/api';
import { notifyError } from '../utils/notify';
import AuthContext from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Bar, Doughnut, Line } from 'react-chartjs-2';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

function Dashboard() {
  const { user } = useContext(AuthContext);
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef(null);

  useEffect(() => {
    if (!exportOpen) return undefined;

    const handleOutsideClick = (event) => {
      if (!exportRef.current?.contains(event.target)) {
        setExportOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [exportOpen]);

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom'
      }
    }
  }), []);

  const downloadReport = useCallback(async (format) => {
    try {
      const response = await aiAPI.generateReport({ type: 'transcript_analytics', format });
      const mimeType = format === 'pdf' ? 'application/pdf' : 'text/csv';
      const blob = new Blob([response.data], { type: mimeType });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `realtime_analytics_report.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      notifyError(t('dashboardUnableGenerateReport', { format: format.toUpperCase() }));
    }
  }, [t]);

  const scrubLabel = useCallback((label) => {
    if (!label || typeof label !== 'string') return label;
    // Scrub administrative noise
    const noise = /^(the|the\s+of|mr|dr|snr|sn|ms|mrs|jacob|seconded|lecturer|chairman|department|student|students|meetings?|discussion|topic|themes?|unknown|inft|marking|regular|page|weekend|end|proceedings)$/i;
    let cleaned = label.trim();
    
    // If it's a multi-word label, strip individual noise words
    const words = cleaned.split(/\s+/).filter(w => !noise.test(w));
    if (words.length > 0) {
      cleaned = words.join(' ');
    }
    
    // Title case
    cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1).toLowerCase();
    
    // Final check - if empty or still noise, fallback
    if (!cleaned || noise.test(cleaned)) return "Strategic Discussion";
    return cleaned;
  }, []);

  const safeChartData = useCallback((data, fallback) => {
    if (!data || typeof data !== 'object') return fallback || { labels: [], datasets: [] };
    
    const rawLabels = Array.isArray(data.labels) ? data.labels : (fallback?.labels || []);
    const cleanLabels = rawLabels.map(l => scrubLabel(l));

    return {
      labels: cleanLabels,
      datasets: Array.isArray(data.datasets) ? data.datasets.map(d => ({
        ...d,
        data: Array.isArray(d.data) ? d.data : []
      })) : Array.isArray(fallback?.datasets) ? fallback.datasets.map(d => ({
        ...d,
        data: Array.isArray(d.data) ? d.data : []
      })) : []
    };
  }, [scrubLabel]);

  const hasChartValues = useCallback((data) => {
    if (!data || !Array.isArray(data.datasets) || data.datasets.length === 0) return false;
    return data.datasets.some((ds) => Array.isArray(ds.data) && ds.data.some((value) => Number(value) > 0));
  }, []);

  const normalizeInsights = useCallback((rawInsights) => {
    if (!Array.isArray(rawInsights)) return [];
    return rawInsights
      .map((item) => {
        if (typeof item === 'string') return item.trim();
        if (item == null) return '';
        return String(item).trim();
      })
      .filter(Boolean)
      .slice(0, 8);
  }, []);

  const normalizeRecentActivity = useCallback((rawActivity) => {
    if (!Array.isArray(rawActivity)) return [];

    return rawActivity
      .map((activity) => {
        if (Array.isArray(activity)) {
          return {
            date: activity[0] || t('dashboardDateNA'),
            meetings_added: Number(activity[1]) || 0,
            segments_added: Number(activity[2]) || 0,
          };
        }

        const date = activity?.date || activity?.day || activity?.created_at || t('dashboardDateNA');
        return {
          date,
          meetings_added: Number(activity?.meetings_added ?? activity?.meetings ?? 0) || 0,
          segments_added: Number(activity?.segments_added ?? activity?.segments ?? 0) || 0,
        };
      })
      .filter((item) => Boolean(item.date))
      .slice(0, 7);
  }, [t]);

  // Separate queries per panel for independent error handling
  const statsQuery = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const dashboardRes = await aiAPI.getDashboard({});
      const dashboardData = dashboardRes?.data || {};
      return {
        totalMeetings: Number(dashboardData?.stats?.totalMeetings) || 0,
        totalSegments: Number(dashboardData?.stats?.totalSegments) || 0,
        actionItems: Number(dashboardData?.stats?.actionItems) || 0,
        themes: Number(dashboardData?.stats?.themes) || 0,
      };
    },
    placeholderData: (prev) => prev,
    refetchInterval: 60000,  // 60s (increased from 30s) - reduced polling for performance
    staleTime: 60000,  // 60s (increased from 30s)
  });

  const chartsQuery = useQuery({
    queryKey: ['dashboard-charts'],
    queryFn: async () => {
      const dashboardRes = await aiAPI.getDashboard({});
      const dashboardData = dashboardRes?.data || {};
      return {
        themeData: dashboardData?.charts?.themeData || null,
        sentimentData: dashboardData?.charts?.sentimentData || null,
        trendsData: dashboardData?.charts?.trendsData || null,
      };
    },
    placeholderData: (prev) => prev,
    refetchInterval: 60000,  // 60s (increased from 30s)
    staleTime: 60000,  // 60s (increased from 30s)
  });

  const insightsQuery = useQuery({
    queryKey: ['dashboard-insights'],
    queryFn: async () => {
      const dashboardRes = await aiAPI.getDashboard({});
      const dashboardData = dashboardRes?.data || {};
      return normalizeInsights(dashboardData?.insights);
    },
    placeholderData: (prev) => prev,
    refetchInterval: 60000,  // 60s (increased from 30s)
    staleTime: 60000,  // 60s (increased from 30s)
  });

  const activityQuery = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: async () => {
      const dashboardRes = await aiAPI.getDashboard({});
      const dashboardData = dashboardRes?.data || {};
      return normalizeRecentActivity(dashboardData?.recentActivity);
    },
    placeholderData: (prev) => prev,
    refetchInterval: 60000,  // 60s (increased from 30s)
    staleTime: 60000,  // 60s (increased from 30s)
  });

  const realtimeQuery = useQuery({
    queryKey: ['dashboard-realtime'],
    queryFn: async () => {
      try {
        const realtimeRes = await aiAPI.getRealtimeDashboard();
        if (realtimeRes?.data?.realtimeAnalytics) {
          return realtimeRes.data.realtimeAnalytics;
        }
      } catch (realtimeError) {
        console.warn('Realtime snapshot unavailable:', realtimeError?.message || realtimeError);
      }
      return {
        stats: {
          totalRecordings: 0,
          avgSentimentScore: 0,
          mostFrequentKeyword: null,
          analyzedCount: 0,
        },
        liveFeed: [],
        charts: null,
      };
    },
    placeholderData: (prev) => prev,
    refetchInterval: 60000,  // 60s (increased from 30s)
    staleTime: 60000,  // 60s (increased from 30s)
  });

  // Check if any critical query is loading
  const isLoading = statsQuery.isPending || chartsQuery.isPending || insightsQuery.isPending || activityQuery.isPending;

  // Extract data with safe defaults
  const stats = statsQuery.data || { totalMeetings: 0, totalSegments: 0, actionItems: 0, themes: 0 };
  const chartData = chartsQuery.data || { themeData: null, sentimentData: null, trendsData: null };
  const insights = Array.isArray(insightsQuery.data) ? insightsQuery.data : [];
  const recentActivity = Array.isArray(activityQuery.data) ? activityQuery.data : [];
  const realtime = realtimeQuery.data || {
    stats: { totalRecordings: 0, avgSentimentScore: 0, mostFrequentKeyword: null, analyzedCount: 0 },
  };

  // All queries updated timestamp (use the latest of all)
  const lastUpdated = new Date().toISOString();

  const resolveDelta = (...candidates) => {
    for (const candidate of candidates) {
      const numeric = Number(candidate);
      if (Number.isFinite(numeric)) {
        return numeric;
      }
    }
    return null;
  };

  const formatDelta = (value) => {
    if (!Number.isFinite(value)) return '';
    const rounded = Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
    return `${value >= 0 ? '+' : ''}${rounded}%`;
  };

  const renderDeltaChip = (value) => {
    if (!Number.isFinite(value)) return null;
    return (
      <span className={`kpi-delta-chip ${value >= 0 ? 'up' : 'down'}`}>
        {formatDelta(value)}
      </span>
    );
  };

  const statDeltas = {
    totalMeetings: resolveDelta(stats?.totalMeetingsDelta, statsQuery.data?.totalMeetingsDelta),
    totalSegments: resolveDelta(stats?.totalSegmentsDelta, statsQuery.data?.totalSegmentsDelta),
    actionItems: resolveDelta(stats?.actionItemsDelta, statsQuery.data?.actionItemsDelta),
    themes: resolveDelta(stats?.themesDelta, statsQuery.data?.themesDelta),
    totalRecordings: resolveDelta(realtime?.stats?.totalRecordingsDelta),
    avgSentimentScore: resolveDelta(realtime?.stats?.avgSentimentScoreDelta),
    analyzedCount: resolveDelta(realtime?.stats?.analyzedCountDelta),
  };

  // Helper to resolve status for each panel independently
  const resolveStatus = (query, hasData) => {
    if (query.isPending && !query.data) return 'loading';
    if (query.isError && !query.data) return 'error';
    return hasData ? 'success' : 'empty';
  };

  const hasTheme = hasChartValues(chartData.themeData);
  const hasSentiment = hasChartValues(chartData.sentimentData);
  const hasTrends = hasChartValues(chartData.trendsData);

  const safeTrendsData = useMemo(
    () => safeChartData(chartData.trendsData, { labels: [], datasets: [] }),
    [chartData.trendsData, safeChartData]
  );

  const trendNonZeroPoints = useMemo(() => {
    if (!safeTrendsData?.datasets?.length) return 0;
    return Math.max(
      ...safeTrendsData.datasets.map((ds) =>
        Array.isArray(ds.data) ? ds.data.filter((v) => Number(v) > 0).length : 0
      )
    );
  }, [safeTrendsData]);

  const isSparseTrendData = safeTrendsData.labels.length <= 2 || trendNonZeroPoints <= 2;

  const monthlyTrendOptions = useMemo(() => ({
    ...chartOptions,
    layout: isSparseTrendData ? {
      padding: {
        top: 28,
        right: 8,
        left: 8,
        bottom: 8,
      },
    } : undefined,
    scales: {
      y: {
        beginAtZero: true,
        suggestedMax: isSparseTrendData ? undefined : undefined,
        grace: '12%',
        title: {
          display: true,
          text: 'Count',
          color: '#5b6b82',
          font: {
            size: 12,
            weight: '700',
          },
          padding: {
            bottom: 8,
          },
        },
        ticks: {
          precision: 0,
          stepSize: isSparseTrendData ? 7 : 10,
          color: '#5b6b82',
          font: {
            size: 12,
            weight: '600',
          },
          padding: 8,
          callback: (value) => Number(value).toLocaleString(),
          mirror: false,
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.18)',
          drawBorder: false,
          tickLength: 6,
        },
        border: {
          display: true,
          color: 'rgba(148, 163, 184, 0.4)',
        },
      },
      x: {
        ticks: {
          autoSkip: false,
          maxRotation: 0,
          minRotation: 0,
          color: '#5b6b82',
          font: {
            size: 12,
            weight: '600',
          },
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.16)',
          drawBorder: false,
        },
      },
    },
    elements: {
      line: {
        tension: 0.25,
      },
      point: {
        radius: isSparseTrendData ? 0 : 4,
        hoverRadius: isSparseTrendData ? 0 : 5,
      },
    },
  }), [chartOptions, isSparseTrendData]);

  const monthlyTrendDisplayData = useMemo(() => {
    const trendPalette = [
      { border: '#1d4ed8', bg: 'rgba(37, 99, 235, 0.38)' },
      { border: '#0f766e', bg: 'rgba(20, 184, 166, 0.38)' },
      { border: '#b45309', bg: 'rgba(245, 158, 11, 0.4)' },
      { border: '#be123c', bg: 'rgba(244, 63, 94, 0.36)' }
    ];

    if (!isSparseTrendData) {
      return {
        ...safeTrendsData,
        datasets: (safeTrendsData.datasets || []).map((ds, index) => {
          const palette = trendPalette[index % trendPalette.length];
          return {
            ...ds,
            borderColor: palette.border,
            backgroundColor: palette.bg,
            pointBackgroundColor: palette.border,
            pointBorderColor: '#ffffff',
            pointHoverBackgroundColor: palette.border,
            pointHoverBorderColor: '#ffffff',
            pointBorderWidth: 2,
            borderWidth: 3,
            fill: false,
          };
        }),
      };
    }

    return {
      ...safeTrendsData,
      datasets: (safeTrendsData.datasets || []).map((ds, index) => {
        const palette = trendPalette[index % trendPalette.length];
        return {
          ...ds,
          borderColor: palette.border,
          backgroundColor: palette.bg,
          borderWidth: 2,
          borderRadius: 6,
          maxBarThickness: 36,
          barPercentage: 0.72,
          categoryPercentage: 0.7,
        };
      }),
    };
  }, [isSparseTrendData, safeTrendsData]);

  const monthlyTrendSummary = useMemo(() => {
    if (!safeTrendsData.labels.length || !safeTrendsData.datasets.length) return [];

    return safeTrendsData.labels.map((label, index) => ({
      label,
      values: safeTrendsData.datasets.map((dataset) => Number(dataset?.data?.[index] || 0)),
    }));
  }, [safeTrendsData]);

  const monthlyTrendLabelsPlugin = useMemo(() => ({
    id: 'monthlyTrendLabels',
    afterDatasetsDraw: (chart) => {
      const { ctx } = chart;
      ctx.save();
      ctx.font = '700 13px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';

      chart.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = chart.getDatasetMeta(datasetIndex);
        if (!meta || meta.hidden) return;

        const datasetLabel = String(dataset?.label || '').toLowerCase();
        const textColor = datasetLabel.includes('meeting') ? '#1d4ed8' : '#0f766e';

        meta.data.forEach((element, index) => {
          const value = Number(dataset.data?.[index] || 0);
          if (!value) return;

          const { x, y } = element.tooltipPosition();
          const yText = Math.max((chart.chartArea?.top || 0) + 14, y - 14);
          const labelText = String(value);

          ctx.lineWidth = 4;
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.98)';
          ctx.strokeText(labelText, x, yText);
          ctx.fillStyle = textColor;
          ctx.fillText(labelText, x, yText);
        });
      });

      ctx.restore();
    }
  }), []);

  if (isLoading && !statsQuery.data) {
    return <LoadingSpinner />;
  }

  return (
    <div className="dashboard dashboard-premium">
      <div className="page-header dashboard-premium-header">
        <div className="header-text-group">
          <h1 className="page-title">{t('welcomeBack')}, {user?.username || t('dashboardUserFallback')}!</h1>
          <p className="page-subtitle">{t('dashboardOverview')}</p>
        </div>
        <div className="dashboard-premium-actions">
          {(user?.role === 'admin' || user?.role === 'super_admin') && (
            <button
              className="btn btn-success btn-sm"
              onClick={() => navigate('/events')}
            >
              <CalendarPlus size={16} /> {t('dashboardCreateEvent')}
            </button>
          )}
          <button className="btn btn-outline btn-sm" onClick={() => navigate('/reports/analytics')}>
            <Presentation size={16} /> Create Slides
          </button>
          <div className="dashboard-export-dropdown" ref={exportRef}>
            <button
              className="btn btn-primary btn-sm dashboard-export-trigger"
              onClick={() => setExportOpen((prev) => !prev)}
              aria-haspopup="menu"
              aria-expanded={exportOpen}
            >
              <Download size={16} /> {t('alExport')} <ChevronDown size={14} />
            </button>
            {exportOpen && (
              <div className="dashboard-export-menu" role="menu" style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, boxShadow: '0 8px 24px rgba(15,23,42,0.08)', zIndex: 200 }}>
                <button className="btn btn-outline btn-sm" onClick={() => { downloadReport('csv'); setExportOpen(false); }} role="menuitem">CSV</button>
                <button className="btn btn-outline btn-sm" onClick={() => { downloadReport('pdf'); setExportOpen(false); }} role="menuitem">PDF</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Board Analytics Section */}
      <div className="dashboard-section-header">
        <h2 className="dashboard-section-title">Board Archive Analytics</h2>
        <p className="dashboard-section-subtitle">Long-term records, themes, and automated action items</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-4 mb-4">
        <div className="stat-card dashboard-premium-stat card-theme-indigo">
          <div className="stat-card-header">
            <span className="stat-label">{t('totalMeetings')}</span>
            <div className="stat-icon-wrapper">
              <FileText size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{stats.totalMeetings}</span>
            {renderDeltaChip(statDeltas.totalMeetings)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">Meetings indexed in database</span>
          </div>
        </div>

        <div className="stat-card dashboard-premium-stat card-theme-emerald">
          <div className="stat-card-header">
            <span className="stat-label">{t('analyzedSegments')}</span>
            <div className="stat-icon-wrapper">
              <BarChart2 size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{stats.totalSegments}</span>
            {renderDeltaChip(statDeltas.totalSegments)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">AI-parsed transcript segments</span>
          </div>
        </div>

        <div className="stat-card dashboard-premium-stat card-theme-amber">
          <div className="stat-card-header">
            <span className="stat-label">{t('actionItems')}</span>
            <div className="stat-icon-wrapper">
              <CheckCircle size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{stats.actionItems}</span>
            {renderDeltaChip(statDeltas.actionItems)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">Pending action points identified</span>
          </div>
        </div>

        <div className="stat-card dashboard-premium-stat card-theme-purple">
          <div className="stat-card-header">
            <span className="stat-label">{t('themesTracked')}</span>
            <div className="stat-icon-wrapper">
              <TrendingUp size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{stats.themes}</span>
            {renderDeltaChip(statDeltas.themes)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">AI-extracted thematic groups</span>
          </div>
        </div>
      </div>

      {/* Realtime Session Analytics Section */}
      <div className="dashboard-section-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <h2 className="dashboard-section-title">Live & Voice Analytics</h2>
          <span className="live-pulse-container">
            <span className="live-pulse-dot"></span>
            <span className="live-pulse-text">Live Stream Active</span>
          </span>
        </div>
        <p className="dashboard-section-subtitle">Real-time meeting transcripts and instant sentiment estimation</p>
      </div>

      {/* Realtime Summary */}
      <div className="grid grid-3 mb-4">
        <div className="stat-card dashboard-premium-stat card-theme-sky">
          <div className="stat-card-header">
            <span className="stat-label">{t('dashboardTotalRecordings')}</span>
            <div className="stat-icon-wrapper">
              <Radio size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{realtime?.stats?.totalRecordings ?? 0}</span>
            {renderDeltaChip(statDeltas.totalRecordings)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">Recorded live audio sessions</span>
          </div>
        </div>

        <div className="stat-card dashboard-premium-stat card-theme-teal">
          <div className="stat-card-header">
            <span className="stat-label">{t('dashboardAvgSentiment')}</span>
            <div className="stat-icon-wrapper">
              <TrendingUp size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{realtime?.stats?.avgSentimentScore ?? 0}</span>
            {renderDeltaChip(statDeltas.avgSentimentScore)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">Average positivity score index</span>
          </div>
        </div>

        <div className="stat-card dashboard-premium-stat card-theme-rose">
          <div className="stat-card-header">
            <span className="stat-label">{t('dashboardAnalyzedRecords')}</span>
            <div className="stat-icon-wrapper">
              <CheckCircle size={18} />
            </div>
          </div>
          <div className="stat-card-body">
            <span className="stat-value">{realtime?.stats?.analyzedCount ?? 0}</span>
            {renderDeltaChip(statDeltas.analyzedCount)}
          </div>
          <div className="stat-card-footer">
            <span className="stat-subtitle">Real-time sessions processed</span>
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-2 mb-4">
        {/* Theme Distribution */}
        <div className="chart-container summary-panel dashboard-premium-panel">
          <div className="chart-header">
            <div className="summary-title-wrap">
              <h3 className="chart-title">{t('themeDistribution')}</h3>
              <p className="summary-subtitle">{t('dashboardThemeSubtitle')}</p>
            </div>
            {lastUpdated && <span className="summary-meta">{t('dashboardUpdated', { time: new Date(lastUpdated).toLocaleTimeString() })}</span>}
          </div>
          <div style={{ height: '300px', padding: '1rem' }}>
            <CardState
              status={resolveStatus(chartsQuery, hasTheme)}
              error={chartsQuery.error?.message}
              emptyMessage={t('dashboardNoThemeData')}
              onRetry={() => chartsQuery.refetch()}
              isRefreshing={chartsQuery.isFetching}
            >
              <Doughnut data={safeChartData(chartData.themeData, { labels: [], datasets: [] })} options={chartOptions} />
            </CardState>
          </div>
        </div>

        {/* Sentiment Analysis */}
        <div className="chart-container summary-panel dashboard-premium-panel">
          <div className="chart-header">
            <div className="summary-title-wrap">
              <h3 className="chart-title">{t('sentimentAnalysis')}</h3>
              <p className="summary-subtitle">{t('dashboardSentimentSubtitle')}</p>
            </div>
            {lastUpdated && <span className="summary-meta">{t('dashboardUpdated', { time: new Date(lastUpdated).toLocaleTimeString() })}</span>}
          </div>
          <div style={{ height: '300px', padding: '1rem' }}>
            <CardState
              status={resolveStatus(chartsQuery, hasSentiment)}
              error={chartsQuery.error?.message}
              emptyMessage={t('dashboardNoSentimentData')}
              onRetry={() => chartsQuery.refetch()}
              isRefreshing={chartsQuery.isFetching}
            >
              <Bar data={safeChartData(chartData.sentimentData, { labels: [], datasets: [] })} options={chartOptions} />
            </CardState>
          </div>
        </div>
      </div>

      {/* Monthly Trends */}
      <div className="chart-container mb-4 summary-panel dashboard-premium-panel">
        <div className="chart-header">
          <div className="summary-title-wrap">
            <h3 className="chart-title">{t('monthlyTrends')}</h3>
            <p className="summary-subtitle">{t('dashboardMonthlyTrendsSubtitle')}</p>
          </div>
          {lastUpdated && <span className="summary-meta">{t('dashboardUpdated', { time: new Date(lastUpdated).toLocaleTimeString() })}</span>}
        </div>
        {isSparseTrendData && monthlyTrendSummary.length > 0 && (
          <div className="monthly-trend-summary-strip">
            {monthlyTrendSummary.map((item) => (
              <div key={item.label} className="monthly-trend-summary-chip">
                <div className="monthly-trend-summary-label">{item.label}</div>
                <div className="monthly-trend-summary-values">
                  <span>Meetings: {item.values[0] ?? 0}</span>
                  <span>Segments: {item.values[1] ?? 0}</span>
                </div>
              </div>
            ))}
          </div>
        )}
        <div style={{ height: '300px', padding: '1rem' }}>
          <CardState
            status={resolveStatus(chartsQuery, hasTrends)}
            error={chartsQuery.error?.message}
            emptyMessage={t('dashboardNoTrendData')}
            onRetry={() => chartsQuery.refetch()}
            isRefreshing={chartsQuery.isFetching}
          >
            {isSparseTrendData ? (
              <Bar data={monthlyTrendDisplayData} options={monthlyTrendOptions} plugins={[monthlyTrendLabelsPlugin]} />
            ) : (
              <Line data={monthlyTrendDisplayData} options={monthlyTrendOptions} />
            )}
          </CardState>
        </div>
      </div>

      {/* Insights and Activity Grid */}
      <div className="grid grid-2 mb-4">
        {/* AI Insights */}
        <div className="chart-container summary-panel dashboard-premium-panel">
          <div className="chart-header">
            <div className="summary-title-wrap">
              <h3 className="chart-title">{t('dashboardAIInsights')}</h3>
              <p className="summary-subtitle">{t('dashboardInsightsSubtitle')}</p>
            </div>
            {lastUpdated && <span className="summary-meta">{t('dashboardUpdated', { time: new Date(lastUpdated).toLocaleTimeString() })}</span>}
          </div>
          <div className="insights-list">
            <CardState
              status={resolveStatus(insightsQuery, insights.length > 0)}
              error={insightsQuery.error?.message}
              emptyMessage={t('dashboardNoInsights')}
              onRetry={() => insightsQuery.refetch()}
              isRefreshing={insightsQuery.isFetching}
            >
              {insights.map((insight, index) => (
                <div key={index} className="insight-item">
                  <div className="insight-icon">
                    <TrendingUp size={16} />
                  </div>
                  <div className="insight-text">{insight}</div>
                </div>
              ))}
            </CardState>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="chart-container summary-panel dashboard-premium-panel">
          <div className="chart-header">
            <div className="summary-title-wrap">
              <h3 className="chart-title">{t('dashboardRecentActivity7')}</h3>
              <p className="summary-subtitle">{t('dashboardRecentActivitySubtitle')}</p>
            </div>
            {lastUpdated && <span className="summary-meta">{t('dashboardUpdated', { time: new Date(lastUpdated).toLocaleTimeString() })}</span>}
          </div>
          <div className="activity-list">
            <CardState
              status={resolveStatus(activityQuery, recentActivity.length > 0)}
              error={activityQuery.error?.message}
              emptyMessage={t('dashboardNoRecentActivity')}
              onRetry={() => activityQuery.refetch()}
              isRefreshing={activityQuery.isFetching}
            >
              {recentActivity.map((activity, index) => (
                <div key={index} className="activity-item">
                  <div className="activity-date">{activity?.date || t('dashboardDateNA')}</div>
                  <div className="activity-stats">
                    {t('dashboardActivityStats', {
                      meetings: activity?.meetings_added ?? 0,
                      segments: activity?.segments_added ?? 0,
                    })}
                  </div>
                </div>
              ))}
            </CardState>
          </div>
        </div>
      </div>

      <div className="mb-4" style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn btn-outline btn-sm" onClick={() => navigate('/voice?history=1')}>
          {t('dashboardViewFullHistory')}
        </button>
      </div>
    </div>
  );
}

export default React.memo(Dashboard);

