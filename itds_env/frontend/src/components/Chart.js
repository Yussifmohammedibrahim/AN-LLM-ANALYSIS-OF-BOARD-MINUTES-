import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  RadialLinearScale,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Bar, Doughnut, Line, Radar } from 'react-chartjs-2';
import { TrendingUp, Calendar, ChevronDown } from 'lucide-react';
import aiAPI from '../api/api';
import { notifyError, notifySuccess } from '../utils/notify';

const THEME_REFRESH_EVENT = 'itds:theme-data-refresh';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  RadialLinearScale,
  Title,
  Tooltip,
  Legend,
  Filler
);

// Custom Chart.js plugin to display labels above bar charts
const chartDataLabelsPlugin = {
  id: 'chartDataLabels',
  afterDatasetsDraw(chart) {
    if (!chart.options.plugins?.chartDataLabels?.display) return;

    const ctx = chart.ctx;
    const fontSize = 14;
    const fontWeight = '700';
    ctx.font = `${fontWeight} ${fontSize}px Arial`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex);
      if (!meta || meta.hidden) return;

      meta.data.forEach((element, elIndex) => {
        // Determine raw value robustly from several possible shapes
        let value = undefined;
        try {
          value = (element?.$context && element.$context.raw) || dataset.data?.[elIndex] || element?.options?.value;
        } catch (e) {
          value = undefined;
        }
        value = (typeof value === 'string') ? Number(value) : value;
        if (typeof value !== 'number' || isNaN(value) || value === 0) return;

        // Compute best x,y for various element types (point, bar, radar, arc)
        let x = element.x;
        let y = element.y;

        if (typeof x === 'undefined' || typeof y === 'undefined') {
          // Attempt center methods
          if (typeof element.getCenterPoint === 'function') {
            const p = element.getCenterPoint();
            x = p.x; y = p.y;
          } else if (element?.tooltipPosition) {
            const p = element.tooltipPosition();
            x = p.x; y = p.y;
          }
        }

        // For bar elements, ensure label sits above the top of bar
        if (typeof element.base !== 'undefined' && typeof element.y !== 'undefined') {
          // element.y is top for positive values, base is baseline
          y = Math.min(element.y, element.base) - 6;
        }

        if (typeof x === 'undefined' || typeof y === 'undefined') return;

        // Offset labels upward for positive values, downward for negative
        const baseOffset = 12;
        const stagger = (datasetIndex % 3) * 10;
        const direction = value >= 0 ? -1 : 1;
        const labelY = y + (direction * (baseOffset + stagger));

        // Draw with enhanced visibility: stronger outline + shadow effect
        const label = Math.round(value);
        ctx.save();
        
        // Shadow effect for depth (darker, offset)
        ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
        ctx.fillText(label, x + 1, labelY + 1);
        
        // Strong white outline for contrast
        ctx.lineWidth = 4.5;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.strokeStyle = '#ffffff';
        ctx.strokeText(label, x, labelY);
        
        // Dark filled text for readability
        ctx.fillStyle = '#0f172a';
        ctx.fillText(label, x, labelY);
        
        ctx.restore();
      });
    });
  }
};

ChartJS.register(chartDataLabelsPlugin);

const THEME_NOISE_WORDS = new Set([
  'meeting', 'meetings', 'discussion', 'discussed', 'agenda', 'item', 'items',
  'today', 'team', 'update', 'updates', 'note', 'notes', 'review', 'reviews',
  'follow', 'followup', 'follow-up', 'action', 'actions', 'point', 'points',
  'page', 'regular', 'department', 'minutes', 'minute', 'general', 'topic', 'topics',
  'the', 'and', 'of', 'to', 'for', 'from', 'with', 'about', 'into', 'during'
]);

const toTitleCase = (value) => String(value || '')
  .replace(/\s+/g, ' ')
  .trim()
  .replace(/\b\w/g, (char) => char.toUpperCase());

const normalizeThemeLabel = (theme, index = 0) => {
  const rawName = String(theme?.name || theme || '').replace(/\s+/g, ' ').trim();
  const keywords = Array.isArray(theme?.keywords) ? theme.keywords : [];

  const keywordLabel = keywords
    .map((keyword) => String(keyword).replace(/[^a-z0-9\s-]/gi, ' ').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .filter((word) => !THEME_NOISE_WORDS.has(word.toLowerCase()))
    .slice(0, 4)
    .join(' ');

  const rawWords = rawName ? rawName.split(' ').filter(Boolean) : [];
  const rawMeaningfulWords = rawWords.filter((word) => !THEME_NOISE_WORDS.has(word.toLowerCase()));
  const looksReadable = rawName
    && rawWords.length <= 4
    && rawMeaningfulWords.length >= 2
    && !/\d/.test(rawName)
    && !/(page|discussion|agenda|update|review|minutes|meeting)/i.test(rawName);

  const candidate = looksReadable
    ? rawName
    : keywordLabel || rawWords.slice(0, 4).join(' ');

  const cleaned = toTitleCase(candidate).replace(/\s+/g, ' ').trim();
  return cleaned || `Theme ${index + 1}`;
};

// Helper to match a backend theme record to the currently selected theme
const themeMatches = (f, selectedId, selectedLabel) => {
  if (!f) return false;
  if (selectedId) {
    if (f.theme_id) return String(f.theme_id) === String(selectedId);
    if (f.id) return String(f.id) === String(selectedId);
  }
  if (selectedLabel) {
    const lbl = normalizeThemeLabel(f);
    return String(lbl).toLowerCase() === String(selectedLabel).toLowerCase();
  }
  return false;
};

// Theme-aware color palettes - automatically adapt to dark/light mode
const getThemeColors = () => {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  
  if (isDark) {
    return {
      primary: '#3b82f6',
      secondary: '#4ade80',
      accent: '#fbbf24',
      danger: '#f87171',
      purple: '#a78bfa',
      info: '#22d3ee',
      muted: '#64748b',
      text: '#e5eefb',
      textSecondary: '#94a3b8',
      grid: 'rgba(148, 163, 184, 0.2)',
      background: 'rgba(59, 130, 246, 0.15)',
      backgroundSolid: 'rgba(59, 130, 246, 0.25)',
      palette: ['#3b82f6', '#4ade80', '#fbbf24', '#f87171', '#a78bfa', '#22d3ee'],
      sentiment: ['#4ade80', '#64748b', '#f87171'], // positive, neutral, negative
    };
  }
  
  // Light mode colors
  return {
    primary: '#2563eb',
    secondary: '#22c55e',
    accent: '#f59e0b',
    danger: '#ef4444',
    purple: '#8b5cf6',
    info: '#0ea5e9',
    muted: '#64748b',
    text: '#1e293b',
    textSecondary: '#64748b',
    grid: 'rgba(148, 163, 184, 0.18)',
    background: 'rgba(37, 99, 235, 0.1)',
    backgroundSolid: 'rgba(37, 99, 235, 0.2)',
    palette: ['#2563eb', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#0ea5e9'],
    sentiment: ['#22c55e', '#64748b', '#ef4444'], // positive, neutral, negative
  };
};

// Custom hook to detect theme changes
const useThemeColors = () => {
  const [themeColors, setThemeColors] = useState(getThemeColors);
  
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setThemeColors(getThemeColors());
    });
    
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    
    return () => observer.disconnect();
  }, []);
  
  return themeColors;
};

const EMPTY_CHART_DATA = {
  themeTrendsData: { labels: [], datasets: [] },
  yearlyComparisonData: { labels: [], datasets: [] },
  themeDistributionData: { labels: [], datasets: [] },
  sentimentTrendData: { labels: [], datasets: [] },
  radarData: { labels: [], datasets: [] }
};

const THEME_TOP_N = 8;

function Charts() {
  // Generate dynamic years - past years through future years
  const generateYears = () => {
    const currentYear = new Date().getFullYear();
    const years = [];
    for (let i = currentYear - 5; i <= currentYear + 3; i++) {
      years.push(i.toString());
    }
    return years;
  };

  const years = useMemo(() => generateYears(), []);

  // Use theme-aware colors
  const themeColors = useThemeColors();

  // Initialize with defaults to avoid empty/null states
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear().toString());
  const [selectedTheme, setSelectedTheme] = useState('');
  const [selectedThemeId, setSelectedThemeId] = useState('');
  const [themes, setThemes] = useState([]); // array of { id, label, raw }
  const themesRef = useRef([]);
  useEffect(() => {
    themesRef.current = themes;
  }, [themes]);
  const [summaryStats, setSummaryStats] = useState({ meetingCount: 0, themeCount: 0 });
  const [loading, setLoading] = useState(false);
  const [chartData, setChartData] = useState(EMPTY_CHART_DATA);
  const [error, setError] = useState('');
  const [summarySource, setSummarySource] = useState('');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
  const [comparisonYear, setComparisonYear] = useState('');
  const [comparisonData, setComparisonData] = useState(null);
  const [showComparison, setShowComparison] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
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

  // Chart refs for capturing images during PDF export
  const trendChartRef = useRef(null);
  const yearlyChartRef = useRef(null);
  const distributionChartRef = useRef(null);
  const sentimentChartRef = useRef(null);
  const radarChartRef = useRef(null);

  // Simple in-memory API cache to reduce duplicate requests during UI interaction
  const apiCache = useMemo(() => new Map(), []);
  const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

  const cachedGet = useCallback(async (url) => {
    const now = Date.now();
    const entry = apiCache.get(url);
    if (entry) {
      // return existing promise if still valid
      if (entry.ts && now - entry.ts < CACHE_TTL && entry.data) return entry.data;
      if (entry.promise) return entry.promise;
    }
    const promise = aiAPI.get(url).then((res) => {
      apiCache.set(url, { ts: Date.now(), data: res });
      return res;
    }).catch((err) => {
      apiCache.delete(url);
      throw err;
    });
    apiCache.set(url, { promise });
    return promise;
  }, [apiCache, CACHE_TTL]);

  const clearThemeCaches = useCallback(() => {
    apiCache.clear();
  }, [apiCache]);

// Chart configurations with theme-aware options
  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: themeColors.text,
          usePointStyle: true,
          padding: 16,
          font: {
            size: 12,
          }
        }
        ,
        // Make legend items act as theme selectors for theme datasets.
        onClick: (e, legendItem, legend) => {
          try {
            const label = legendItem.text;
            // If user clicked the Meetings dataset, preserve default toggle behavior
            if (label === 'Meetings') {
              const ci = legend.chart;
              const index = legendItem.datasetIndex;
              const meta = ci.getDatasetMeta(index);
              meta.hidden = meta.hidden === null ? !ci.data.datasets[index].hidden : null;
              ci.update();
              return;
            }

            // For theme labels: toggle selection (click to select, click again to clear)
            const clickedTheme = String(label || '').trim();
            if (!clickedTheme) return;
            const found = themes.find(t => t.label === clickedTheme);
            if (found) {
              if (found.id === selectedThemeId) {
                setSelectedThemeId('');
                setSelectedTheme('');
              } else {
                setSelectedThemeId(found.id);
                setSelectedTheme(found.label);
              }
            } else {
              // Fallback: toggle by label
              if (clickedTheme === selectedTheme) {
                setSelectedTheme('');
              } else {
                setSelectedTheme(clickedTheme);
              }
            }
          } catch (err) {
            // ignore and fallback to default
          }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.92)',
        titleColor: '#ffffff',
        bodyColor: '#f8fafc',
        borderColor: themeColors.grid,
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
      },
      // Custom plugin to display bar labels above bars
      chartDataLabels: {
        display: true,
        anchor: 'end',
        align: 'top',
        offset: 10,
        font: {
          weight: 'bold',
          size: 12
        },
        color: '#0f172a',
        formatter: (value) => {
          return value > 0 ? `${Math.round(value)}` : '';
        }
      }
    },
    scales: {
      x: {
        ticks: {
          color: themeColors.textSecondary,
        },
        grid: {
          color: themeColors.grid,
        }
      },
      y: {
        beginAtZero: true,
        grace: '15%',
        ticks: {
          color: themeColors.textSecondary,
        },
        grid: {
          color: themeColors.grid,
        }
      }
    },
    // Ensure labels don't get clipped by the chart area
    layout: {
      padding: {
        top: 20
      }
    }
  }), [themeColors, selectedTheme, selectedThemeId, themes]);

  // Yearly comparison chart options with grouped bars
  const yearlyChartOptions = useMemo(() => ({
    ...chartOptions,
    scales: {
      ...chartOptions.scales,
      x: {
        ...chartOptions.scales.x,
        stacked: false,
      },
      y: {
        ...chartOptions.scales.y,
        stacked: false,
      }
    }
  }), [chartOptions]);

  const hasChartValues = (data) => {
    if (!data || !Array.isArray(data.datasets) || data.datasets.length === 0) return false;
    return data.datasets.some((ds) => Array.isArray(ds.data) && ds.data.some((value) => Number(value) > 0));
  };

  // Helper: Capture chart canvases as PNG images
  const captureChartImages = async () => {
    const images = {};
    const refs = {
      'trend_chart': trendChartRef,
      'yearly_chart': yearlyChartRef,
      'distribution_chart': distributionChartRef,
      'sentiment_chart': sentimentChartRef,
      'radar_chart': radarChartRef
    };

    for (const [name, ref] of Object.entries(refs)) {
      try {
        // react-chartjs-2 exposes chart instance via current property
        const chartInstance = ref?.current;
        if (chartInstance) {
          // Get canvas from the chart instance - try multiple paths
          let canvas = null;
          if (chartInstance.canvas) {
            canvas = chartInstance.canvas;
          } else if (chartInstance.ctx?.canvas) {
            canvas = chartInstance.ctx.canvas;
          } else if (chartInstance.chartInstance?.canvas) {
            canvas = chartInstance.chartInstance.canvas;
          }
          
          if (canvas) {
            try {
              // Create a high-DPI copy of the canvas to improve export clarity
              const ratio = Math.max(2, window.devicePixelRatio || 1);
              const origWidth = canvas.width;
              const origHeight = canvas.height;
              const hiResCanvas = document.createElement('canvas');
              hiResCanvas.width = Math.floor(origWidth * ratio);
              hiResCanvas.height = Math.floor(origHeight * ratio);
              const hiCtx = hiResCanvas.getContext('2d');
              // Scale drawing to preserve visual size but increase pixel density
              hiCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
              hiCtx.drawImage(canvas, 0, 0);
              images[name] = hiResCanvas.toDataURL('image/png');
              console.log(`✓ Captured ${name} (hi-res x${ratio})`);
            } catch (hiErr) {
              // Fallback to original canvas export
              images[name] = canvas.toDataURL('image/png');
              console.warn(`Captured ${name} with fallback export due to:`, hiErr);
            }
          } else {
            console.warn(`No canvas found for ${name}, checking DOM...`);
            // Fallback: find canvas element in parent
            const canvasEl = ref?.current?.querySelector?.('canvas') || 
                            ref?.current?.parentElement?.querySelector?.('canvas');
            if (canvasEl) {
              try {
                const ratio = Math.max(2, window.devicePixelRatio || 1);
                const origWidth = canvasEl.width;
                const origHeight = canvasEl.height;
                const hiResCanvas = document.createElement('canvas');
                hiResCanvas.width = Math.floor(origWidth * ratio);
                hiResCanvas.height = Math.floor(origHeight * ratio);
                const hiCtx = hiResCanvas.getContext('2d');
                hiCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
                hiCtx.drawImage(canvasEl, 0, 0);
                images[name] = hiResCanvas.toDataURL('image/png');
                console.log(`✓ Captured ${name} via DOM query (hi-res x${ratio})`);
              } catch (domErr) {
                images[name] = canvasEl.toDataURL('image/png');
                console.warn(`Captured ${name} via DOM query (fallback):`, domErr);
              }
            }
          }
        }
      } catch (err) {
        console.warn(`Failed to capture ${name}:`, err);
      }
    }
    console.log('Captured images:', Object.keys(images).length, 'charts');
    return images;
  };

  // PDF Export function — capture charts and POST to backend for PDF generation
  const exportToPDF = async () => {
    try {
      let pdfContent = `Analytics & Trends Report\n`;
      pdfContent += `Generated: ${new Date().toLocaleString()}\n\n`;
      pdfContent += `===== REPORT SUMMARY =====\n`;
      pdfContent += `Year: ${selectedYear}\n`;
      pdfContent += `Theme: ${selectedTheme || 'All Themes'}\n`;
      pdfContent += `Auto-Refresh: ${autoRefreshEnabled ? 'Enabled' : 'Disabled'}\n\n`;
      pdfContent += `===== QUICK STATS =====\n`;
      pdfContent += `Meetings Analyzed: ${summaryStats.meetingCount}\n`;
      pdfContent += `${selectedTheme ? 'Theme' : 'Themes'} Analyzed: ${summaryStats.themeCount}\n`;
      pdfContent += `Source: ${summarySource}\n\n`;
      pdfContent += `===== YEARLY COMPARISON DATA =====\n`;
      if (chartData.yearlyComparisonData && chartData.yearlyComparisonData.labels) {
        pdfContent += `Years: ${chartData.yearlyComparisonData.labels.join(', ')}\n`;
        chartData.yearlyComparisonData.datasets.forEach((ds) => {
          pdfContent += `${ds.label}: ${ds.data.join(', ')}\n`;
        });
      }
      pdfContent += `\n===== THEME DISTRIBUTION =====\n`;
      if (chartData.themeDistributionData && chartData.themeDistributionData.labels) {
        chartData.themeDistributionData.labels.forEach((label, i) => {
          pdfContent += `${label}: ${chartData.themeDistributionData.datasets[0].data[i]}\n`;
        });
      }

      // Capture chart images
      const chartImages = await captureChartImages();
      console.log('Captured chart images:', Object.keys(chartImages), chartImages);

      // Build FormData with text content and images
      const formData = new FormData();
      formData.append('title', `analytics-report-${selectedYear}`);
      formData.append('text', pdfContent);
      
      let imageCount = 0;
      Object.entries(chartImages).forEach(([name, dataUrl]) => {
        if (dataUrl) {
          try {
            // Convert base64 data URL to Blob
            const [, data] = dataUrl.split(',');
            if (!data) {
              console.warn(`Invalid data URL for ${name}`);
              return;
            }
            const bstr = atob(data);
            const n = bstr.length;
            const u8arr = new Uint8Array(n);
            for (let i = 0; i < n; i++) {
              u8arr[i] = bstr.charCodeAt(i);
            }
            const imageBlob = new Blob([u8arr], { type: 'image/png' });
            formData.append('images', imageBlob, `${name}.png`);
            imageCount++;
            console.log(`✓ Added image: ${name}.png (${imageBlob.size} bytes)`);
          } catch (blobErr) {
            console.error(`Failed to convert ${name} to blob:`, blobErr);
          }
        }
      });

      console.log(`Sending FormData with ${imageCount} images via axios...`);

      // Use axios instance with proper FormData handling
      // Note: axios automatically sets Content-Type: multipart/form-data for FormData
      const resp = await aiAPI.post('/api/ai/export/pdf', formData, {
        responseType: 'blob',
        headers: {
          // Don't set Content-Type - let axios/browser set it automatically for FormData
        },
        timeout: 30000
      });

      console.log(`✓ Received response: status=${resp.status}, size=${resp.data.size} bytes`);
      
      const pdfBlob = resp.data;
      const url = URL.createObjectURL(pdfBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `analytics-report-${selectedYear}-${new Date().getTime()}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      notifySuccess('PDF with charts exported successfully!');
    } catch (err) {
      console.error('PDF export failed:', err);
      console.error('Error details:', {
        message: err.message,
        response: err.response?.status,
        responseData: err.response?.data,
        stack: err.stack
      });
      notifyError(`PDF export failed: ${err.response?.status || err.message || 'Unknown error'}. Check console.`);
    }
  };

  // Fetch comparison year data
  const loadComparisonData = useCallback(async () => {
    if (!comparisonYear || comparisonYear === selectedYear) return;
    try {
      const [trendsResp, freqResp] = await Promise.all([
        cachedGet(`/api/ai/theme-trends?year=${comparisonYear}${selectedTheme ? `&theme=${encodeURIComponent(selectedTheme)}` : ''}`),
        cachedGet(`/api/ai/theme-frequency?year=${comparisonYear}&top_n=${THEME_TOP_N}`)
      ]);
      const trendsData = trendsResp?.data || {};
      const freqData = Array.isArray(freqResp?.data) ? freqResp.data : [];
      
      setComparisonData({
        meetingCount: Number(trendsData?.statistics?.total_meetings || 0),
        themeCount: new Set(freqData.map(f => normalizeThemeLabel(f).toLowerCase()).filter(Boolean)).size
      });
    } catch (err) {
      console.error('Error loading comparison data:', err);
      setComparisonData(null);
    }
  }, [comparisonYear, selectedYear, selectedTheme, cachedGet]);

  // Load comparison data when comparisonYear changes
  useEffect(() => {
    if (showComparison && comparisonYear) {
      loadComparisonData();
    }
  }, [comparisonYear, showComparison, loadComparisonData]);

  // Load chart data with proper error handling
  const loadChartData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      // Fetch all relevant endpoints for robust data
      const [trendsResponse, sentimentResponse, selectedFrequencyResponse, allFrequencyResponse] = await Promise.all([
        cachedGet(`/api/ai/theme-trends?year=${selectedYear}${selectedTheme ? `&theme=${encodeURIComponent(selectedTheme)}` : ''}`),
        cachedGet(`/api/ai/themes/sentiment?year=${selectedYear}${selectedTheme ? `&theme=${encodeURIComponent(selectedTheme)}` : ''}`),
        // Use one shared top_n across all charts so all theme counts stay consistent
        cachedGet(`/api/ai/theme-frequency?year=${selectedYear}&top_n=${THEME_TOP_N}${selectedTheme ? `&theme=${encodeURIComponent(selectedTheme)}` : ''}`),
        cachedGet(`/api/ai/theme-frequency?year=${selectedYear}&top_n=${THEME_TOP_N}`)
      ]);

      // Defensive: fallback to empty objects if missing
      const trendsData = trendsResponse?.data || {};
      const sentimentData = sentimentResponse?.data || {};
      const selectedFrequencyData = Array.isArray(selectedFrequencyResponse?.data) ? selectedFrequencyResponse.data : [];
      const allFrequencyData = Array.isArray(allFrequencyResponse?.data) ? allFrequencyResponse.data : [];
      const liveThemes = Array.isArray(themesRef.current) ? themesRef.current : [];

const summaryThemeSources = liveThemes.length > 0
        ? liveThemes
        : (Array.isArray(trendsData.themes) ? trendsData.themes : []);

const meetingCount = Number(trendsData?.statistics?.total_meetings || trendsData?.total_meetings || 0);
      
      // Calculate total theme mentions for Quick Stats
      // For selected theme: prefer summing the per-year selectedThemeResponses (if available),
      // otherwise fall back to the current year's statistic or matched frequency entry.
      // For "All Themes": sum all theme frequencies for the selected year.
      let themeCount = 0;
      if (selectedTheme && selectedTheme !== '') {
        // If per-year counts for this selected theme were requested below, prefer their sum
        // (we'll compute selectedThemeResponses shortly). For now, try to use the returned
        // trends statistic for the current year, otherwise fall back to frequency entries.
        themeCount = Number(trendsData?.statistics?.theme_total_mentions || 0);
        if ((themeCount === 0 || Number.isNaN(themeCount)) && selectedFrequencyData.length > 0) {
          const matched = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
          if (matched) {
            themeCount = Number(matched.total_mentions || matched.frequency || matched.meeting_count || 0);
          }
        }
        // As a final safety, if we still have no themeCount, use the sum of monthly values for the selected theme
        if ((themeCount === 0 || Number.isNaN(themeCount)) && Array.isArray(selectedFrequencyData) && selectedFrequencyData.length > 0) {
          const matched = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
          if (matched && matched.monthly_distribution) {
            themeCount = Object.values(matched.monthly_distribution).reduce((s, v) => s + Number(v || 0), 0);
          }
        }
      } else {
        // All themes - show the number of unique themes for the current year
        const allThemeSources = allFrequencyData.length > 0 ? allFrequencyData : summaryThemeSources;
        if (Array.isArray(allThemeSources)) {
          const unique = new Set(allThemeSources.map(t => normalizeThemeLabel(t).toLowerCase()).filter(Boolean));
          themeCount = unique.size;
        } else {
          themeCount = 0;
        }
      }

      // Defer updating summaryStats until we compute per-year selectedThemeResponses
      // (we'll set summaryStats after computing yearly arrays below).

      const lineThemeSources = allFrequencyData.length > 0
        ? allFrequencyData
        : summaryThemeSources;

      // --- Meeting Frequency (Theme Trends) ---
      const monthLabels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const monthlyTrends = trendsData.monthly_trends || {};
      const monthlyThemeTrends = trendsData.theme_monthly_trends || {};
      const meetingTrendValues = monthLabels.map((_, i) => {
        const month = selectedYear + '-' + String(i + 1).padStart(2, '0');
        return Number(monthlyTrends[month] || 0);
      });

// If backend didn't return a specific monthly series, fall back to theme-frequency monthly_distribution
      let fallbackMonthly = {};
      if ((!monthlyThemeTrends || Object.keys(monthlyThemeTrends).length === 0) && (selectedThemeId || selectedTheme)) {
        const matched = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme))
          || lineThemeSources.find(f => themeMatches(f, selectedThemeId, selectedTheme));
        if (matched && matched.monthly_distribution) {
          fallbackMonthly = matched.monthly_distribution;
        }
      }
      const selectedThemeValues = monthLabels.map((_, i) => {
        const month = selectedYear + '-' + String(i + 1).padStart(2, '0');
        return Number(monthlyThemeTrends[month] || fallbackMonthly[month] || 0);
      });

      // Helper to read monthly distribution values from various backend shapes
      const getMonthlyValue = (distribution, year, monthIndex) => {
        if (!distribution) return 0;
        // Prefer keys like '2026-05'
        const mm = String(monthIndex + 1).padStart(2, '0');
        const keyYMD = `${year}-${mm}`;
        if (typeof distribution[keyYMD] !== 'undefined') return Number(distribution[keyYMD] || 0);
        // Fallback to numeric keys '5' or '05'
        if (typeof distribution[String(monthIndex + 1)] !== 'undefined') return Number(distribution[String(monthIndex + 1)] || 0);
        if (typeof distribution[mm] !== 'undefined') return Number(distribution[mm] || 0);
        // Fallback to array-like monthly list
        if (Array.isArray(distribution) && typeof distribution[monthIndex] !== 'undefined') return Number(distribution[monthIndex] || 0);
        return 0;
      };

      const aggregatedThemeValues = monthLabels.map((_, i) => {
        return lineThemeSources.reduce((sum, item) => {
          const distribution = item?.monthly_distribution || item?.monthly || item?.monthly_distribution_map || {};
          return sum + getMonthlyValue(distribution, selectedYear, i);
        }, 0);
      });

// Build individual theme datasets when no specific theme is selected
      const themeDatasets = selectedTheme
        ? [{
            label: selectedTheme,
            data: selectedThemeValues,
            borderColor: '#16a34a',
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.35,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 6,
            order: 2
          }]
          : lineThemeSources.map((theme, idx) => {
            const distribution = theme?.monthly_distribution || theme?.monthly || theme?.monthly_distribution_map || {};
            const themeValues = monthLabels.map((_, i) => getMonthlyValue(distribution, selectedYear, i));
            const colors = ['#16a34a', '#2563eb', '#8b5cf6', '#f59e0b', '#ef4444'];
            const themeLabel = String(normalizeThemeLabel(theme, idx) || `Theme ${idx + 1}`).trim();
            return {
              label: themeLabel,
              data: themeValues,
              borderColor: colors[idx % colors.length],
              backgroundColor: 'transparent',
              fill: false,
              tension: 0.35,
              borderWidth: 2,
              pointRadius: 3,
              pointHoverRadius: 5,
              order: 2 + idx
            };
          });

          // Debugging: log sources when running in development to verify mapping
          // eslint-disable-next-line no-console
          console.debug('Theme dataset sources', { selectedYear, lineThemeSources: lineThemeSources.slice(0, 5), aggregatedThemeValues, themeDatasets });

      const themeLineVisible = selectedTheme
        ? selectedThemeValues.some((v) => Number(v) > 0)
        : aggregatedThemeValues.some((v) => Number(v) > 0);

      // Debug logs to help verify values in the browser console
      // eslint-disable-next-line no-console
      console.debug('Theme line data', { selectedTheme, monthlyThemeTrends, fallbackMonthly, selectedThemeValues, aggregatedThemeValues, selectedFrequencyData, allFrequencyData, liveThemes, summaryThemeSources, lineThemeSources, themeLineVisible });
      const newThemeTrendsData = {
        labels: monthLabels,
        datasets: [
          {
            label: 'Meetings',
            data: meetingTrendValues,
            borderColor: '#2563eb',
            backgroundColor: 'rgba(37, 99, 235, 0.12)',
            fill: true,
            tension: 0.4,
            borderWidth: 2,
            pointRadius: 3,
            order: 1
          },
          ...themeDatasets
        ]
      };

// --- Yearly Comparison ---
      // Show all years up to selected year
      const yearLabels = years.filter(y => parseInt(y) <= parseInt(selectedYear));
      
      // Always get meetings and theme data - display both bars regardless of selected theme
      // For meetings: fetch from theme-trends endpoint
      // For themes: calculate total theme occurrences from meeting frequency endpoint
      const [meetingsResponses, themeFrequencyResponses, selectedThemeResponses] = await Promise.all([
        Promise.all(
          yearLabels.map(async (year) => {
            try {
              const response = await cachedGet(`/api/ai/theme-trends?year=${year}`);
              return Number(response.data?.statistics?.total_meetings || response.data?.total_meetings || 0);
            } catch (e) {
              return 0;
            }
          })
        ),
        Promise.all(
          yearLabels.map(async (year) => {
            try {
              const response = await cachedGet(`/api/ai/theme-frequency?year=${year}&top_n=${THEME_TOP_N}`);
              const freqData = Array.isArray(response?.data) ? response.data : [];
              // Return the number of unique theme names for this year (dedupe by name)
              const uniqueNames = new Set(freqData.map(f => normalizeThemeLabel(f).toLowerCase()).filter(Boolean));
              return uniqueNames.size;
            } catch (e) {
              return 0;
            }
          })
        ),
        selectedTheme && selectedTheme !== ''
          ? Promise.all(
              yearLabels.map(async (year) => {
                try {
                  const resp = await cachedGet(`/api/ai/theme-frequency?year=${year}&top_n=${THEME_TOP_N}`);
                  const freqData = Array.isArray(resp?.data) ? resp.data : [];
                  const matched = freqData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
                  if (matched) return Number(matched.meeting_count || matched.total_mentions || matched.frequency || 0);
                  return 0;
                } catch (e) {
                  return 0;
                }
              })
            )
          : Promise.resolve([])
      ]);
      
      // Ensure numeric arrays aligned with labels (fill missing years with 0)
      const ensureNumericArray = (arr, length) => {
        const out = new Array(length).fill(0);
        for (let i = 0; i < length; i++) {
          out[i] = Number((Array.isArray(arr) && typeof arr[i] !== 'undefined') ? arr[i] : 0) || 0;
        }
        return out;
      };

      const meetingsData = ensureNumericArray(meetingsResponses, yearLabels.length);
      // Show theme mentions for selected theme, otherwise show total theme mentions from frequency data
      const rawThemesData = (selectedTheme && selectedTheme !== '') ? selectedThemeResponses : themeFrequencyResponses;
      const themesData = ensureNumericArray(rawThemesData, yearLabels.length);

      // Now compute a final themeCount for Quick Stats. Prefer the summed per-year
      // selectedThemeResponses when a theme is selected; otherwise show number of themes.
      let finalThemeCount = themeCount;
      if (selectedTheme && selectedTheme !== '') {
        const sumSelected = Array.isArray(selectedThemeResponses) ? selectedThemeResponses.reduce((s, v) => s + Number(v || 0), 0) : 0;
        if (sumSelected > 0) {
          finalThemeCount = sumSelected;
        } else {
          // Fallback to the matched frequency entry for the current year
          const matched = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
          if (matched) finalThemeCount = Number(matched.total_mentions || matched.frequency || matched.meeting_count || 0);
        }
      } else {
        const allThemeSources = allFrequencyData.length > 0 ? allFrequencyData : summaryThemeSources;
        if (Array.isArray(allThemeSources)) {
          const unique = new Set(allThemeSources.map(t => normalizeThemeLabel(t).toLowerCase()).filter(Boolean));
          finalThemeCount = unique.size;
        } else {
          finalThemeCount = 0;
        }
      }

      setSummaryStats({ meetingCount, themeCount: finalThemeCount });

      const newYearlyComparisonData = {
        labels: yearLabels,
        datasets: [
          {
            label: 'Meetings',
            data: meetingsData,
            backgroundColor: themeColors.primary || '#2563eb',
            borderRadius: 4
          },
          {
            label: selectedTheme ? 'Theme Mentions' : 'Themes',
            data: themesData,
            backgroundColor: themeColors.secondary || '#22c55e',
            borderRadius: 4
          }
        ]
      };

// --- Theme Distribution ---
      // Build distribution data - show selected theme if specific theme selected, otherwise show all themes
      let themeDistributionLabels = [];
      let themeDistributionData = [];
      
      if (selectedTheme && selectedTheme !== '') {
        // When a specific theme is selected, show that theme's frequency
        const matchedTheme = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme))
          || allFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
        if (matchedTheme) {
          const label = String(normalizeThemeLabel(matchedTheme) || selectedTheme || 'Unknown Theme').trim();
          themeDistributionLabels = [label];
          themeDistributionData = [Number(matchedTheme.meeting_count || matchedTheme.frequency || matchedTheme.total_mentions || 0)];
        } else {
          // Fallback: show the selected theme name with a placeholder value
          themeDistributionLabels = [selectedTheme];
          themeDistributionData = [selectedThemeValues.reduce((a, b) => a + b, 0)];
        }
      } else {
        // Show ALL themes when "All Themes" is selected
        const allThemeSources = allFrequencyData.length > 0 ? allFrequencyData : summaryThemeSources;
        themeDistributionLabels = allThemeSources.map((t, idx) => {
          const label = String(normalizeThemeLabel(t, idx) || `Theme ${idx + 1}`).trim();
          return label;
        });
        themeDistributionData = allThemeSources.map(t => Number(t.meeting_count || t.frequency || t.total_mentions || 0));
      }
      
      const newThemeDistributionData = {
        labels: themeDistributionLabels,
        datasets: [{
          data: themeDistributionData,
          backgroundColor: ['#2563eb', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#a78bfa'],
          borderWidth: 0
        }]
      };

      // Provide a short source hint for summary counts
      // selectedTheme -> source 'per-year-sum' if selectedThemeResponses had values,
      // or 'frequency-match' if matched the current year's frequency entry.
      if (selectedTheme && selectedTheme !== '') {
        const sumSelected = Array.isArray(selectedThemeResponses) ? selectedThemeResponses.reduce((s, v) => s + Number(v || 0), 0) : 0;
        if (sumSelected > 0) setSummarySource('per-year-sum');
        else {
          const matched = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
          setSummarySource(matched ? 'frequency-match' : 'monthly-sum');
        }
      } else {
        setSummarySource('themes-count');
      }

      // --- Sentiment Trend ---
      let sentimentDistribution = sentimentData.distribution || {};
      if (sentimentDistribution && typeof sentimentDistribution === 'object') {
        ['positive', 'neutral', 'negative'].forEach((k) => {
          if (typeof sentimentDistribution[k] !== 'number') sentimentDistribution[k] = 0;
        });
      } else {
        sentimentDistribution = { positive: 0, neutral: 0, negative: 0 };
      }
      const newSentimentTrendData = {
        labels: ['Positive', 'Neutral', 'Negative'],
        datasets: [{
          label: 'Sentiment %',
          data: [
            Number(sentimentDistribution.positive || 0),
            Number(sentimentDistribution.neutral || 0),
            Number(sentimentDistribution.negative || 0)
          ],
          backgroundColor: ['#22c55e', '#64748b', '#ef4444'],
          borderWidth: 0
        }]
      };

// --- Theme Performance Radar ---
      // Build radar data - show selected theme if specific theme selected, otherwise show all themes
      let radarChartLabels = [];
      let radarChartData = [];
      
      if (selectedTheme && selectedTheme !== '') {
        // When a specific theme is selected, show that theme's confidence
        const matchedRadarTheme = selectedFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme))
          || allFrequencyData.find(f => themeMatches(f, selectedThemeId, selectedTheme));
        if (matchedRadarTheme) {
          const label = String(normalizeThemeLabel(matchedRadarTheme) || selectedTheme || 'Unknown Theme').trim();
          radarChartLabels = [label];
          const mentions = Number(matchedRadarTheme.meeting_count || matchedRadarTheme.frequency || matchedRadarTheme.total_mentions || 0);
          const growth = Number(matchedRadarTheme.growth_rate || 0);
          radarChartData = [Math.max(0, Math.min(100, mentions * 5 + Math.max(0, growth)))];
        } else {
          // Fallback: show the selected theme name with a placeholder value
          radarChartLabels = [selectedTheme];
          const totalMentions = selectedThemeValues.reduce((a, b) => a + b, 0);
          radarChartData = [Math.max(0, Math.min(100, totalMentions * 5))];
        }
      } else {
        // Show ALL themes when "All Themes" is selected
        const allRadarSources = allFrequencyData.length > 0 ? allFrequencyData : summaryThemeSources;
        radarChartLabels = allRadarSources.map((t, idx) => {
          const label = String(normalizeThemeLabel(t, idx) || `Theme ${idx + 1}`).trim();
          return label;
        });
        radarChartData = allRadarSources.map(t => {
          const mentions = Number(t.meeting_count || t.frequency || t.total_mentions || 0);
          const growth = Number(t.growth_rate || 0);
          return Math.max(0, Math.min(100, mentions * 5 + Math.max(0, growth)));
        });
      }
      
      const newRadarData = {
        labels: radarChartLabels,
        datasets: [{
          label: 'Theme Confidence',
          data: radarChartData,
          backgroundColor: 'rgba(37, 99, 235, 0.2)',
          borderColor: '#2563eb',
          pointBackgroundColor: '#2563eb'
        }]
      };

      setChartData({
        themeTrendsData: newThemeTrendsData,
        yearlyComparisonData: newYearlyComparisonData,
        themeDistributionData: newThemeDistributionData,
        sentimentTrendData: newSentimentTrendData,
        radarData: newRadarData
      });

    } catch (error) {
      console.error('Error loading chart data:', error);
      setError('Could not load chart data from backend.');
      setChartData(EMPTY_CHART_DATA);
    } finally {
      setLoading(false);
    }
}, [selectedYear, selectedTheme, selectedThemeId, years, cachedGet, themeColors]);

  // Listen for theme-refresh broadcasts and reload chart data
  useEffect(() => {
    const handleThemeRefresh = () => {
      try {
        clearThemeCaches();
        if (typeof loadChartData === 'function') loadChartData();
      } catch (e) {
        console.warn('Theme refresh handler failed', e);
      }
    };

    window.addEventListener(THEME_REFRESH_EVENT, handleThemeRefresh);
    return () => window.removeEventListener(THEME_REFRESH_EVENT, handleThemeRefresh);
  }, [clearThemeCaches, loadChartData]);

  // Load year-scoped themes from the same source used by all chart panels
  useEffect(() => {
    const loadThemes = async () => {
      try {
        const response = await aiAPI.get(`/api/ai/theme-frequency?year=${selectedYear}&top_n=${THEME_TOP_N}`);
        const themeRows = Array.isArray(response.data) ? response.data : [];
        if (themeRows.length > 0) {
          const items = themeRows.map((theme, index) => ({
            id: theme.theme_id || theme.id || `theme-${index}`,
            label: normalizeThemeLabel(theme, index),
            raw: theme
          })).filter(Boolean);
          // Deduplicate by id keeping first
          const seen = new Set();
          const dedup = [];
          for (const it of items) {
            if (!seen.has(it.id)) {
              seen.add(it.id);
              dedup.push(it);
            }
          }
          setThemes(dedup);
          // Keep current selection if still present; otherwise reset to All Themes
          if (selectedThemeId && dedup.some((t) => String(t.id) === String(selectedThemeId))) {
            const found = dedup.find((t) => String(t.id) === String(selectedThemeId));
            setSelectedTheme(found?.label || '');
          } else {
            setSelectedThemeId('');
            setSelectedTheme('');
          }
        } else {
          setThemes([]);
          setSelectedThemeId('');
          setSelectedTheme('');
        }
      } catch (error) {
        console.warn('Could not load year themes from API:', error.message);
        setThemes([]);
        setSelectedThemeId('');
        setSelectedTheme('');
      }
    };
    loadThemes();
  }, [selectedYear, selectedThemeId]);

  // Debounced loadChartData when selection changes
  useEffect(() => {
    const id = setTimeout(() => {
      loadChartData();
    }, 300);
    return () => clearTimeout(id);
  }, [selectedYear, selectedTheme, loadChartData]);

  // Auto-refresh polling when enabled (every 30 seconds)
  useEffect(() => {
    if (!autoRefreshEnabled) return;
    const interval = setInterval(() => {
      loadChartData();
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefreshEnabled, loadChartData]);

  const LoadingSpinner = () => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '300px' }}>
      <div className="spinner"></div>
    </div>
  );

  return (
    <div className="dashboard">
      <div className="page-header flex justify-between items-center analytics-trends-header">
        <div className="analytics-trends-title-wrap">
          <h1 className="page-title analytics-trends-title">Analytics & Trends</h1>
          <p className="page-subtitle">Visualize meeting patterns and insights</p>
        </div>
        <div className="flex gap-2 items-center analytics-trends-controls">
          <select
            className="form-select"
            style={{ width: 'auto' }}
            value={selectedYear}
            onChange={(e) => setSelectedYear(e.target.value)}
            disabled={loading}
          >
            {years.map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
          <select
            className="form-select"
            style={{ width: 'auto' }}
            value={selectedThemeId}
            onChange={(e) => {
              const id = e.target.value;
              setSelectedThemeId(id);
              const found = themes.find(t => t.id === id);
              setSelectedTheme(found ? found.label : '');
            }}
            disabled={loading}
          >
            <option value="">All Themes</option>
            {themes.map(theme => (
              <option key={theme.id} value={theme.id}>{theme.label}</option>
            ))}
          </select>
          <button
            className={`btn btn-sm ${autoRefreshEnabled ? 'btn-success' : 'btn-outline'}`}
            onClick={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
            title={autoRefreshEnabled ? 'Auto-refresh is ON (every 30s)' : 'Click to enable auto-refresh'}
          >
            {autoRefreshEnabled ? '🔄 Live (ON)' : '⏸ Live (OFF)'}
          </button>
          <button
            className={`btn btn-sm ${showComparison ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setShowComparison(!showComparison)}
            title="Compare two years side-by-side"
          >
            {showComparison ? '📊 Compare (ON)' : '📊 Compare'}
          </button>
          <div className="export-dropdown" ref={exportRef} style={{ position: 'relative' }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setExportOpen((s) => !s)}
              aria-haspopup="menu"
              aria-expanded={exportOpen}
              disabled={loading}
            >
              📤 Export <span style={{ marginLeft: 8 }} /> <ChevronDown size={14} />
            </button>
            {exportOpen && (
              <div className="export-menu" role="menu" style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', minWidth: '180px', padding: '0.5rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, boxShadow: '0 10px 28px rgba(15,23,42,0.12)', zIndex: 200 }}>
                <button className="btn btn-outline btn-sm" style={{ display: 'flex', width: '100%', justifyContent: 'flex-start', gap: '0.5rem' }} onClick={() => { exportToPDF(); setExportOpen(false); }} role="menuitem">📄 Export PDF</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {!!error && (
        <div className="card mb-4" style={{ color: '#b91c1c' }}>
          <div className="card-body">{error}</div>
        </div>
      )}

      {showComparison && (
        <div className="card mb-4" style={{ background: '#f0f9ff', borderLeft: '4px solid #0ea5e9' }}>
          <div className="card-body">
            <h3 style={{ marginBottom: '1rem', color: '#0369a1' }}>📊 Year Comparison</h3>
            <div className="flex gap-2 items-center mb-4">
              <label style={{ fontWeight: '500' }}>Compare with year:</label>
              <select
                className="form-select"
                style={{ width: 'auto' }}
                value={comparisonYear}
                onChange={(e) => setComparisonYear(e.target.value)}
              >
                <option value="">Select a year...</option>
                {years.map(year => (
                  year !== selectedYear && <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
            
            {comparisonYear && comparisonData && (
              <div className="grid grid-2 gap-4">
                <div style={{ background: '#fff', padding: '1rem', borderRadius: '0.375rem', border: '1px solid #e5e7eb' }}>
                  <h4>{selectedYear} (Selected)</h4>
                  <div style={{ marginTop: '0.5rem' }}>
                    <div>Meetings: <strong>{summaryStats.meetingCount}</strong></div>
                    <div>Themes: <strong>{summaryStats.themeCount}</strong></div>
                  </div>
                </div>
                <div style={{ background: '#fff', padding: '1rem', borderRadius: '0.375rem', border: '1px solid #e5e7eb' }}>
                  <h4>{comparisonYear} (Comparison)</h4>
                  <div style={{ marginTop: '0.5rem' }}>
                    <div>
                      Meetings: <strong>{comparisonData.meetingCount}</strong>
                      <span style={{ marginLeft: '0.5rem', color: summaryStats.meetingCount > comparisonData.meetingCount ? '#22c55e' : '#ef4444', fontSize: '0.875rem' }}>
                        {summaryStats.meetingCount > comparisonData.meetingCount ? '↑' : '↓'} 
                        {Math.abs(((summaryStats.meetingCount - comparisonData.meetingCount) / comparisonData.meetingCount * 100).toFixed(1))}%
                      </span>
                    </div>
                    <div>
                      Themes: <strong>{comparisonData.themeCount}</strong>
                      <span style={{ marginLeft: '0.5rem', color: summaryStats.themeCount > comparisonData.themeCount ? '#22c55e' : '#ef4444', fontSize: '0.875rem' }}>
                        {summaryStats.themeCount > comparisonData.themeCount ? '↑' : '↓'}
                        {Math.abs(((summaryStats.themeCount - comparisonData.themeCount) / comparisonData.themeCount * 100).toFixed(1))}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {loading && <LoadingSpinner />}

      {!loading && (
        <>
{/* Theme Trends Over Time */}
          <div className="chart-container mb-4">
            <div className="chart-header">
              <h3 className="chart-title">
                <TrendingUp size={20} style={{ marginRight: '0.5rem', display: 'inline' }} />
                {selectedTheme ? `${selectedTheme} - Meeting Frequency` : 'Meeting Frequency'}
              </h3>
              <p className="chart-context">Dynamic NLP trend view scoped to the selected year.</p>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    // Export theme trends to CSV
                    const labels = chartData.themeTrendsData.labels || [];
                    const datasets = chartData.themeTrendsData.datasets || [];
                    const rows = [ ['Month', ...datasets.map(d => d.label)] ];
                    for (let i = 0; i < labels.length; i++) {
                      rows.push([labels[i], ...datasets.map(d => Number(d.data[i] || 0))]);
                    }
                    const csv = rows.map(r => r.join(',')).join('\n');
                    const blob = new Blob([csv], { type: 'text/csv' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${selectedTheme ? selectedTheme.replace(/\s+/g,'_') : 'meeting_frequency'}.csv`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Export CSV
                </button>
              </div>
            </div>
            <div style={{ height: '300px', padding: '1rem' }}>
                {hasChartValues(chartData.themeTrendsData)
                ? <Line ref={trendChartRef} data={chartData.themeTrendsData} options={chartOptions} />
                : <div className="no-data">No trend data available for selected year.</div>}
            </div>
          </div>

          {/* Charts Grid */}
          <div className="grid grid-2 mb-4">
{/* Yearly Comparison */}
            <div className="chart-container">
              <div className="chart-header">
                <h3 className="chart-title">
                  <Calendar size={20} style={{ marginRight: '0.5rem', display: 'inline' }} />
                  Yearly Comparison
                </h3>
              </div>
              <div style={{ height: '300px', padding: '1rem' }}>
                {hasChartValues(chartData.yearlyComparisonData)
                  ? <Bar ref={yearlyChartRef} data={chartData.yearlyComparisonData} options={yearlyChartOptions} />
                  : <div className="no-data">No yearly comparison data available.</div>}
              </div>
            </div>

            {/* Theme Distribution */}
            <div className="chart-container">
              <div className="chart-header">
                <h3 className="chart-title">Theme Distribution</h3>
                <p className="chart-context">Dynamic extraction from segment text for this year.</p>
              </div>
              <div style={{ height: '300px', padding: '1rem' }}>
                {hasChartValues(chartData.themeDistributionData)
                  ? <Doughnut ref={distributionChartRef} data={chartData.themeDistributionData} options={chartOptions} />
                  : <div className="no-data">No theme distribution data available.</div>}
              </div>
            </div>
          </div>

          {/* Sentiment Trend */}
          <div className="chart-container mb-4">
            <div className="chart-header">
              <h3 className="chart-title">Sentiment Trend Over Time</h3>
            </div>
            <div style={{ height: '300px', padding: '1rem' }}>
              {hasChartValues(chartData.sentimentTrendData)
                ? <Bar ref={sentimentChartRef} data={chartData.sentimentTrendData} options={chartOptions} />
                : <div className="no-data">No sentiment data available for selected year.</div>}
            </div>
          </div>

          {/* Additional Charts */}
          <div className="grid grid-3 mb-4">
            {/* Theme Performance Radar */}
            <div className="chart-container">
              <div className="chart-header">
                <h3 className="chart-title">Theme Performance</h3>
              </div>
              <div style={{ height: '250px', padding: '1rem' }}>
                {hasChartValues(chartData.radarData)
                  ? <Radar ref={radarChartRef} data={chartData.radarData} options={chartOptions} />
                  : <div className="no-data">No theme confidence data available.</div>}
              </div>
            </div>

            {/* Quick Stats */}
            <div className="chart-container">
              <div className="chart-header">
                <h3 className="chart-title">Quick Stats</h3>
              </div>
              <div className="card-body">
                <div className="mb-4">
                  <div className="flex justify-between mb-1">
                    <span className="text-sm">Meetings</span>
                    <span className="text-sm font-semibold">{summaryStats.meetingCount}</span>
                  </div>
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{
                        width: summaryStats.meetingCount > 0 ? '100%' : '0%',
                        background: 'linear-gradient(90deg, #2563eb 0%, #22c55e 100%)',
                        boxShadow: summaryStats.meetingCount > 0 ? '0 0 10px rgba(34, 197, 94, 0.35)' : 'none'
                      }}
                    ></div>
                  </div>
                </div>
                <div className="mb-4">
                  <div className="flex justify-between mb-1">
                    <span className="text-sm">{selectedTheme ? 'Theme Mentions' : 'Themes'}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span className="text-sm font-semibold">{summaryStats.themeCount}</span>
                      <span className="text-xs" style={{ color: '#6b7280' }}>
                        ({summarySource === 'per-year-sum' && 'total across years'}{summarySource === 'frequency-match' && 'from this year'}{summarySource === 'themes-count' && 'distinct themes'}{summarySource === 'monthly-sum' && 'from monthly'})
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-sm">Selected Year</span>
                    <span className="text-sm font-semibold">{selectedYear}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Chart Type Indicator */}
            <div className="chart-container">
              <div className="chart-header">
                <h3 className="chart-title">Status</h3>
              </div>
              <div className="card-body">
                <div className="mb-2">
                  <span className="text-sm">Current Theme:</span>
                  <p className="text-sm font-semibold" style={{ color: '#2563eb', marginTop: '0.5rem' }}>
                    {selectedTheme}
                  </p>
                </div>
                <div>
                  <span className="text-sm">All charts are live and responsive</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default React.memo(Charts);
