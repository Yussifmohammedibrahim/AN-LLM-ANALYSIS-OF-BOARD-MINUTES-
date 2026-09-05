import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { TrendingUp, AlertCircle, Loader, RefreshCw, ShieldAlert, Presentation } from 'lucide-react';
import { Link } from 'react-router-dom';
import { notifyError, notifySuccess } from '../utils/notify';
import AuthContext from '../context/AuthContext';
import { CheckCircle } from 'lucide-react';
import { useConfirm } from './ConfirmProvider';
import './TrendAnalysisDashboard.css';

const THEME_TOP_N = 8;
const THEME_REFRESH_EVENT = 'itds:theme-data-refresh';
const THEME_REFRESH_STORAGE_KEY = 'itds_theme_data_refresh';

// Shared promise cache to dedupe identical API requests across component instances
const pendingRequests = new Map();

// Optimized line chart component with memoization
const LineChart = React.memo(({ data, title }) => {
  const [hoveredPoint, setHoveredPoint] = useState(null);

  if (!data || data.length === 0) {
    return <div className="trend-chart-empty">No data available</div>;
  }

  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const hasSinglePoint = data.length === 1;
  const chartPoints = data.map((d, i) => {
    const x = hasSinglePoint ? 50 : (i / (data.length - 1)) * 100;
    const y = 100 - (d.value / maxValue) * 100;
    return { ...d, x, y };
  });

  const hoverBands = chartPoints.map((p, i) => {
    const left = i === 0 ? 0 : (chartPoints[i - 1].x + p.x) / 2;
    const right = i === chartPoints.length - 1 ? 100 : (p.x + chartPoints[i + 1].x) / 2;
    return { left, width: Math.max(1, right - left), point: p };
  });

  const polylinePoints = chartPoints
    .map((p) => `${p.x},${p.y}`)
    .join(' ');

  const singlePointY = hasSinglePoint ? chartPoints[0].y : null;

  return (
    <div className="trend-chart">
      <h4>{title}</h4>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="trend-chart-svg">
        {hoverBands.map((band, i) => (
          <rect
            key={`hover-band-${i}`}
            x={band.left}
            y="0"
            width={band.width}
            height="100"
            className="trend-chart-hover-band"
            onMouseEnter={() => setHoveredPoint(band.point)}
            onMouseLeave={() => setHoveredPoint(null)}
          />
        ))}
        {hasSinglePoint && (
          <>
            <line
              x1="0"
              y1={singlePointY}
              x2="100"
              y2={singlePointY}
              className="trend-chart-baseline"
            />
            <line
              x1="50"
              y1="0"
              x2="50"
              y2="100"
              className="trend-chart-center-guide"
            />
          </>
        )}
        <polyline points={polylinePoints} className="trend-chart-line" />
        {chartPoints.map((p, i) => (
          <g key={`${p.label}-${i}`}>
            <circle
              cx={p.x}
              cy={p.y}
              r={hasSinglePoint ? 3.4 : 2.2}
              className="trend-chart-point"
            />
            {(hasSinglePoint || data.length <= 6) && (
              <text
                x={p.x}
                // If label is very near top, push it down; otherwise show above point
                y={p.y <= 6 ? Math.min(p.y + 10, 96) : Math.max(p.y - 6, 6)}
                textAnchor="middle"
                className="trend-chart-point-label"
                stroke="#ffffff"
                strokeWidth={0.9}
                paintOrder="stroke"
              >
                {p.value}
              </text>
            )}
          </g>
        ))}
      </svg>
      {hoveredPoint && (
        <div
          className="trend-chart-tooltip"
          style={{ left: `${hoveredPoint.x}%`, top: `${hoveredPoint.y}%` }}
        >
          <div className="trend-chart-tooltip-month">{hoveredPoint.label}</div>
          <div className="trend-chart-tooltip-value">Meetings: {hoveredPoint.value}</div>
        </div>
      )}
      <div className="trend-chart-labels">
        {data.map((d, i) => (
          <span
            key={i}
            className="trend-chart-label"
            style={{ left: `${hasSinglePoint ? 50 : (i / (data.length - 1)) * 100}%` }}
            title={d.label}
          >
            {d.label.substring(5)}
          </span>
        ))}
      </div>
    </div>
  );
});

LineChart.displayName = 'LineChart';

const TrendAnalysisDashboard = () => {
  const { user } = React.useContext(AuthContext);
  const confirm = useConfirm();
  const [year, setYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [trends, setTrends] = useState(null);
  const [themes, setThemes] = useState([]);
  const [emerging, setEmerging] = useState([]);
  const [recurring, setRecurring] = useState([]);
  const [sentiment, setSentiment] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [dataCache, setDataCache] = useState({});

  const API_BASE_URL = process.env.REACT_APP_API_URL || `http://${window.location.hostname}:5001`;
  const REQUEST_TIMEOUT = 30000; // 30 second timeout

  const fetchWithTimeout = useCallback(async (url, options = {}) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }, []);

  // Cached loader that dedupes identical requests using a shared promise map
  const cachedLoadJson = useCallback(async (url, name, force = false) => {
    if (force) {
      pendingRequests.delete(url);
    }
    if (pendingRequests.has(url)) {
      return pendingRequests.get(url);
    }

    const promise = (async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetchWithTimeout(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!response || !response.ok) {
          console.warn(`${name} endpoint not ready:`, response && response.status);
          return null;
        }
        return await response.json();
      } catch (error) {
        console.warn(`${name} endpoint failed:`, error);
        return null;
      } finally {
        // keep the resolved value cached only for the life of the pending promise; callers
        // should persist returned JSON into component cache if they want longer term caching
        pendingRequests.delete(url);
      }
    })();

    pendingRequests.set(url, promise);
    return promise;
  }, [fetchWithTimeout]);

  const fetchTrendData = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    try {
      const cacheKey = `trends_${year}`;
      
      if (forceRefresh) {
        setDataCache((prev) => {
          const next = { ...prev };
          delete next[cacheKey];
          return next;
        });
      }

      // Return cached data if available
      if (!forceRefresh && dataCache[cacheKey]) {
        const cached = dataCache[cacheKey];
        setTrends(cached.trends);
        setThemes(cached.themes);
        setEmerging(cached.emerging);
        setRecurring(cached.recurring);
        setSentiment(Array.isArray(cached.sentiment) ? cached.sentiment : []);
        setAnomalies(cached.anomalies || []);
        setLoading(false);
        return;
      }
      
      const [trendsData, themesData] = await Promise.all([
        cachedLoadJson(`${API_BASE_URL}/api/ai/theme-trends?year=${year}`, 'Trends', forceRefresh),
        cachedLoadJson(`${API_BASE_URL}/api/ai/theme-frequency?year=${year}&top_n=${THEME_TOP_N}`, 'Themes', forceRefresh),
      ]);

      // Cache the data
      const cachedData = {
        trends: trendsData,
        themes: Array.isArray(themesData) ? themesData : Array.isArray(themesData?.themes) ? themesData.themes : [],
        emerging: [],
        recurring: [],
        sentiment: [],
        anomalies: [],
      };
      setDataCache(prev => ({ ...prev, [cacheKey]: cachedData }));
      
      // Update state with received data
      if (trendsData) setTrends(trendsData);
      if (cachedData.themes) setThemes(cachedData.themes);
      if (cachedData.emerging) setEmerging(cachedData.emerging);
      if (cachedData.recurring) setRecurring(cachedData.recurring);
      if (cachedData.sentiment) setSentiment(cachedData.sentiment);

      // Load the slower supporting sections in the background so the dashboard can render sooner.
      Promise.allSettled([
        cachedLoadJson(`${API_BASE_URL}/api/ai/emerging-themes?year=${year}`, 'Emerging', forceRefresh),
        cachedLoadJson(`${API_BASE_URL}/api/ai/recurring-issues?year=${year}`, 'Recurring', forceRefresh),
        cachedLoadJson(`${API_BASE_URL}/api/ai/sentiment-trends?year=${year}`, 'Sentiment', forceRefresh),
        cachedLoadJson(`${API_BASE_URL}/api/ai/theme-anomalies?year=${year}&notify=true`, 'Anomalies', forceRefresh),
      ]).then((results) => {
        const [emergingResult, recurringResult, sentimentResult, anomaliesResult] = results;

        if (emergingResult.status === 'fulfilled' && Array.isArray(emergingResult.value)) {
          setEmerging(emergingResult.value);
        }

        if (recurringResult.status === 'fulfilled' && Array.isArray(recurringResult.value)) {
          setRecurring(recurringResult.value);
        }

        if (sentimentResult.status === 'fulfilled' && Array.isArray(sentimentResult.value)) {
          setSentiment(sentimentResult.value);
        }

        if (anomaliesResult.status === 'fulfilled' && Array.isArray(anomaliesResult.value?.anomalies)) {
          setAnomalies(anomaliesResult.value.anomalies);
        }

        setDataCache((prev) => ({
          ...prev,
          [cacheKey]: {
            trends: trendsData,
            themes: Array.isArray(themesData) ? themesData : Array.isArray(themesData?.themes) ? themesData.themes : [],
            emerging: emergingResult.status === 'fulfilled' && Array.isArray(emergingResult.value) ? emergingResult.value : [],
            recurring: recurringResult.status === 'fulfilled' && Array.isArray(recurringResult.value) ? recurringResult.value : [],
            sentiment: sentimentResult.status === 'fulfilled' && Array.isArray(sentimentResult.value) ? sentimentResult.value : [],
            anomalies: anomaliesResult.status === 'fulfilled' && Array.isArray(anomaliesResult.value?.anomalies) ? anomaliesResult.value.anomalies : [],
          },
        }));
      });
    } catch (error) {
      notifyError('Failed to load trend data');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL, year, dataCache, cachedLoadJson]);

  const handleVerifyTheme = useCallback(async (theme) => {
    try {
      const themeName = theme.name || theme.theme;
      const meetingId = theme.meeting_id; // Optional context

      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/ai/verify-theme`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ meeting_id: meetingId, theme_name: themeName })
      });

      if (response.ok) {
        notifySuccess(`Theme "${themeName}" verified successfully`);
        fetchTrendData(true);
      } else {
        notifyError('Failed to verify theme');
      }
    } catch (error) {
      notifyError('Error during verification');
      console.error(error);
    }
  }, [API_BASE_URL, fetchTrendData]);

  const handleRegenerateThemes = useCallback(async () => {
    const result = await confirm({
      title: 'Regenerate Themes',
      message: 'This will purge all low-quality/noise themes and re-run AI analysis for this year. Continue?',
      actions: [{ label: 'Regenerate', value: 'regenerate', variant: 'danger' }],
      cancelLabel: 'Cancel',
    });
    if (result.action !== 'regenerate') return;
    
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/ai/regenerate-themes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ year })
      });

      if (response.ok) {
        notifySuccess('AI themes regenerated successfully');
        fetchTrendData(true);
      } else {
        notifyError('Failed to regenerate themes');
      }
    } catch (error) {
      notifyError('Error during regeneration');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL, year, fetchTrendData, confirm]);

  // Debounce helper for user-driven year changes to avoid repeated fetches
  const debounceTimerRef = React.useRef(null);
  const scheduleFetch = useCallback((force = false, wait = 300) => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchTrendData(force);
    }, wait);
  }, [fetchTrendData]);

  useEffect(() => {
    fetchTrendData();
  }, [fetchTrendData]);

  useEffect(() => {
    const handleThemeRefresh = () => {
      fetchTrendData(true);
    };

    const handleStorageRefresh = (event) => {
      if (event.key === THEME_REFRESH_STORAGE_KEY) {
        fetchTrendData(true);
      }
    };

    window.addEventListener(THEME_REFRESH_EVENT, handleThemeRefresh);
    window.addEventListener('storage', handleStorageRefresh);

    return () => {
      window.removeEventListener(THEME_REFRESH_EVENT, handleThemeRefresh);
      window.removeEventListener('storage', handleStorageRefresh);
    };
  }, [fetchTrendData]);

  const chartData = useMemo(() => 
    trends && trends.trends
      ? trends.trends.map((t) => ({
          label: t.month,
          value: t.meeting_count,
        }))
      : [],
    [trends]
  );

  const sentimentChartData = useMemo(() => 
    Array.isArray(sentiment) && sentiment.length > 0
      ? sentiment.map((s) => ({
          label: s.month,
          value: s.positive_rate,
        }))
      : [],
    [sentiment]
  );

  // Hook: detect when an element enters the viewport
  const useOnScreen = (ref, rootMargin = '0px', threshold = 0.05) => {
    const [isIntersecting, setIntersecting] = useState(false);
    useEffect(() => {
      if (!ref.current) return;
      const observer = new IntersectionObserver(
        ([entry]) => setIntersecting(entry.isIntersecting),
        { root: null, rootMargin, threshold }
      );
      observer.observe(ref.current);
      return () => observer.disconnect();
    }, [ref, rootMargin, threshold]);
    return isIntersecting;
  };

  // LazyRender: renders children only when visible; shows fallback until then
  const LazyRender = ({ children, fallback = null, minHeight = 160 }) => {
    const containerRef = useRef(null);
    const visible = useOnScreen(containerRef);
    return (
      <div ref={containerRef} style={{ minHeight }}>
        {visible ? children : fallback}
      </div>
    );
  };

  const uniqueThemes = useMemo(() => {
    if (!Array.isArray(themes) || themes.length === 0) return [];
    const map = new Map();
    for (const t of themes) {
      const key = String(t?.theme_id || t?.name || '').toLowerCase();
      if (!key) continue;
      if (!map.has(key)) map.set(key, t);
    }
    return Array.from(map.values());
  }, [themes]);

  const criticalAnomalies = useMemo(
    () => (anomalies || []).filter((item) => String(item?.severity || '').toLowerCase() === 'critical'),
    [anomalies]
  );

  const resolveThemeLabel = useCallback((theme) => {
    const primary = String(theme?.theme || theme?.name || '').trim();
    // Filter out common noise words, titles, and generic labels
    const isNoise = /^(the|the\s+of|mr|dr|snr|sn|ms|mrs|jacob|seconded|lecturer|chairman|department|student|students|meetings?|discussion|topic|themes?|unknown|inft|marking|regular|page|weekend)$/i.test(primary);
    
    if (primary && !isNoise && !/^unknown( theme)?$/i.test(primary) && !/^theme(s)?$/i.test(primary) && !/^topic$/i.test(primary)) return primary;

    const keyword = Array.isArray(theme?.keywords) && theme.keywords.length > 0
      ? theme.keywords.map((item) => String(item || '').trim()).filter(Boolean).slice(0, 4).join(' ')
      : '';
    if (keyword && !/^theme(s)?$/i.test(keyword) && !/^topic$/i.test(keyword)) return keyword;

    return String(theme?.theme_id || 'Cluster').trim();
  }, []);

  const filterKeywords = useCallback((keywords) => {
    if (!keywords || !Array.isArray(keywords)) return [];
    const trashWords = ['snr', 'sn', 'mr', 'dr', 'ms', 'mrs', 'jacob', 'seconded', 'lecturer', 'chairman', 'inft', 'marking', 'regular', 'page', 'weekend'];
    return keywords
      .map(k => String(k || '').trim())
      .filter(k => {
        const low = k.toLowerCase();
        return low.length > 1 && !trashWords.some(t => low.includes(t));
      });
  }, []);

  const renderConfidenceBadge = useCallback((theme) => {
    const confidence = Number(theme?.confidence);
    const hasConfidence = Number.isFinite(confidence) && confidence > 0;
    const reviewRequired = Boolean(theme?.review_required) || (hasConfidence && confidence < 0.65);
    const needsValidation = Boolean(theme?.requires_validation) || (hasConfidence && confidence >= 0.65 && confidence < 0.75);
    const trusted = Boolean(theme?.trusted) || (hasConfidence && confidence >= 0.75);

    if (!hasConfidence && !reviewRequired && !needsValidation && !trusted) {
      return null;
    }

    if (reviewRequired) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span className="trend-confidence-badge trend-confidence-review">Needs Review</span>
          {(user?.role === 'admin' || user?.role === 'super_admin') && (
            <button 
              className="trend-verify-btn" 
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleVerifyTheme(theme); }}
              title="Verify and Approve Theme"
            >
              <CheckCircle size={14} /> Verify
            </button>
          )}
        </div>
      );
    }
    if (needsValidation) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span className="trend-confidence-badge trend-confidence-validate">Validate</span>
          {(user?.role === 'admin' || user?.role === 'super_admin') && (
            <button 
              className="trend-verify-btn" 
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleVerifyTheme(theme); }}
              title="Approve Theme"
            >
              <CheckCircle size={14} /> Approve
            </button>
          )}
        </div>
      );
    }
    return <span className="trend-confidence-badge trend-confidence-trusted">Trusted</span>;
  }, [user, handleVerifyTheme]);

  return (
    <div className="trend-analysis-dashboard">
      {/* Header */}
      <div className="trend-dashboard-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
          <h1 style={{ margin: '0', flexShrink: 0 }}>Trends Analysis Dashboard</h1>
          <p className="trend-header-subtitle">Visualize meeting patterns and insights</p>
        </div>
        <div className="trend-dashboard-controls">
          <select
            value={year}
            onChange={(e) => { const y = parseInt(e.target.value); setYear(y); scheduleFetch(false); }}
            className="trend-year-selector"
            disabled={loading}
          >
            {[2024, 2025, 2026, 2027].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <span className="trend-total-count" title={`${uniqueThemes.length || 0} total themes`}>{uniqueThemes.length || 0} total</span>
          <Link to={`/reports/analytics?year=${year}`} className="trend-ppt-link" title="Create themed presentation slides">
            <Presentation size={16} /> Create Slides
          </Link>
          {(user?.role === 'admin' || user?.role === 'super_admin') && (
            <button
              onClick={handleRegenerateThemes}
              disabled={loading}
              className="trend-regenerate-button"
              title="Purge noise and re-run AI theme analysis"
            >
              <RefreshCw size={16} className={loading ? 'trend-spinning' : ''} /> Regenerate AI Data
            </button>
          )}
          <button
            onClick={() => fetchTrendData(true)}
            disabled={loading}
            className="trend-refresh-button"
            title="Refresh data"
          >
            <RefreshCw size={18} className={loading ? 'trend-spinning' : ''} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="trend-loading">
          <Loader size={32} className="trend-spinner" />
          <p>Loading trend data...</p>
        </div>
      ) : (
        <>
          {/* Key Statistics */}
          {trends && (
            <div className="trend-statistics-grid">
              <div className="trend-stat-card">
                <div className="trend-stat-value">{trends.statistics?.total_meetings || 0}</div>
                <div className="trend-stat-label">Total Meetings</div>
              </div>
              <div className="trend-stat-card">
                <div className="trend-stat-value">{trends.statistics?.average_per_month?.toFixed(1) || 0}</div>
                <div className="trend-stat-label">Avg/Month</div>
              </div>
              <div className="trend-stat-card">
                <div className="trend-stat-value">{trends.statistics?.peak_count || 0}</div>
                <div className="trend-stat-label">Peak Month</div>
              </div>
              <div className="trend-stat-card">
                <div className="trend-stat-value">{uniqueThemes.length}</div>
                <div className="trend-stat-label">Unique Themes</div>
              </div>
              <div className="trend-stat-card">
                <div className="trend-stat-value">{criticalAnomalies.length}</div>
                <div className="trend-stat-label">Critical Anomalies</div>
              </div>
            </div>
          )}

          {criticalAnomalies.length > 0 && (
            <div className="trend-critical-alert-box">
              <ShieldAlert size={20} />
              <div>
                <h3>Critical Theme Anomalies</h3>
                <p>{criticalAnomalies.length} anomaly signals detected. Review flagged themes before decision use.</p>
              </div>
            </div>
          )}

          {/* Insight Box */}
          {trends && trends.insight && (
            <div className="trend-insight-box">
              <TrendingUp size={20} />
              <div>
                <h3>Key Insight</h3>
                <p>{trends.insight}</p>
              </div>
            </div>
          )}

          {/* Charts Section */}
          <div className="trend-charts-section">
              <div className="trend-chart-wrapper">
                <LazyRender
                  fallback={<div className="trend-chart-skeleton"><div className="skeleton-box" style={{height:140}}>Loading chart...</div></div>}
                >
                  <LineChart data={chartData} title="Meeting Frequency Over Time" />
                </LazyRender>
              </div>
              {sentimentChartData.length > 0 && (
                <div className="trend-chart-wrapper">
                  <LazyRender
                    fallback={<div className="trend-chart-skeleton"><div className="skeleton-box" style={{height:140}}>Loading chart...</div></div>}
                  >
                    <LineChart data={sentimentChartData} title="Positive Sentiment Trend" />
                  </LazyRender>
                </div>
              )}
          </div>

          {/* Trends Table */}
          {trends && trends.trends && (
            <div className="trend-table-section">
              <h2>Monthly Trends</h2>
              <div className="trend-table-wrapper">
                <table className="trend-table">
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Meetings</th>
                      <th>Growth Rate</th>
                      <th>Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trends.trends.map((t, i) => (
                      <tr key={i}>
                        <td className="trend-table-month">{t.month}</td>
                        <td className="trend-table-count">{t.meeting_count}</td>
                        <td className="trend-table-growth">
                          <span className={`trend-growth-${t.growth_rate > 0 ? 'positive' : t.growth_rate < 0 ? 'negative' : 'neutral'}`}>
                            {t.growth_rate > 0 ? '+' : ''}
                            {t.growth_rate.toFixed(1)}%
                          </span>
                        </td>
                        <td className="trend-table-trend">
                          <span className={`trend-badge-${t.trend}`}>{t.trend.toUpperCase()}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Emerging Themes */}
          {emerging && emerging.length > 0 && (
            <div className="trend-section">
              <h2>📈 Emerging Themes</h2>
              <p className="trend-section-subtitle">Rapidly growing themes requiring attention</p>
              <div className="trend-items-grid">
                {emerging.slice(0, 6).map((theme, i) => (
                  <div key={i} className="trend-theme-card trend-emerging">
                    <div className="trend-card-header">
                      <h4>{resolveThemeLabel(theme)}</h4>
                      <div className="trend-card-badges">
                        {renderConfidenceBadge(theme)}
                        <span className="trend-growth-badge">+{theme.growth_rate.toFixed(0)}%</span>
                      </div>
                    </div>
                    <p className="trend-card-keywords">{filterKeywords(theme.keywords).slice(0, 3).join(', ')}</p>
                    <p className="trend-card-stat">{theme.total_mentions} mentions</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recurring Issues */}
          {recurring && recurring.length > 0 && (
            <div className="trend-section">
              <h2>🔁 Recurring Issues</h2>
              <p className="trend-section-subtitle">Topics appearing in multiple meetings</p>
              <div className="trend-items-grid">
                {recurring.slice(0, 6).map((issue, i) => (
                  <div key={i} className="trend-theme-card trend-recurring">
                    <div className="trend-card-header">
                      <h4>{resolveThemeLabel(issue)}</h4>
                      <div className="trend-card-badges">
                        {renderConfidenceBadge(issue)}
                        <span className="trend-freq-badge">{issue.frequency.toFixed(0)}%</span>
                      </div>
                    </div>
                    <p className="trend-card-keywords">{filterKeywords(issue.keywords).slice(0, 3).join(', ')}</p>
                    <p className="trend-card-stat">
                      {issue.meeting_count} of {issue.total_meetings} meetings
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top Themes */}
          {uniqueThemes && uniqueThemes.length > 0 && (
            <div className="trend-section">
              <h2>🎯 Top Themes</h2>
              <p className="trend-section-subtitle">Most frequently discussed topics</p>
              <div className="trend-items-grid">
                {uniqueThemes.slice(0, 6).map((theme, i) => (
                  <div key={i} className="trend-theme-card">
                    <div className="trend-card-header">
                      <h4>{resolveThemeLabel(theme)}</h4>
                    </div>
                    <div className="trend-card-status-row">
                      {renderConfidenceBadge(theme)}
                      <span className={`trend-status-badge trend-${theme.growth_trend}`}>
                        {theme.growth_trend.charAt(0).toUpperCase() + theme.growth_trend.slice(1)}
                      </span>
                    </div>
                    <p className="trend-card-keywords">{filterKeywords(theme.keywords).slice(0, 3).join(', ')}</p>
                    <p className="trend-card-stat">{theme.total_mentions} total mentions</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {!trends && !themes.length && !emerging.length && !recurring.length && (
            <div className="trend-empty-state">
              <AlertCircle size={48} />
              <h3>No trend data available</h3>
              <p>
                Trend data will appear once meetings with themes and discussions are recorded. Make sure to run
                theme extraction on your meetings first.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default React.memo(TrendAnalysisDashboard);
