import React, { useEffect, useState } from 'react';
import { Download, TrendingUp, Calendar, FileText, BarChart3, Smile, TriangleAlert, Sparkles } from 'lucide-react';
import ExecutiveSummaryCard from './ExecutiveSummaryCard';
import { Link, useLocation } from 'react-router-dom';
import { notifyError, notifySuccess } from '../utils/notify';
import { reportsAPI } from '../api/api';
import './ReportsPage.css';

const ReportsPage = () => {
  const location = useLocation();
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [downloading, setDownloading] = useState(false);
  const [pptDownloading, setPptDownloading] = useState(false);
  const [showPptModal, setShowPptModal] = useState(false);
  const [templateTheme, setTemplateTheme] = useState('corporate');
  const [slideMode, setSlideMode] = useState('auto');
  const [topNThemes, setTopNThemes] = useState(6);
  const [includeAnomalies, setIncludeAnomalies] = useState(true);
  const [includeSpeakerNotes, setIncludeSpeakerNotes] = useState(true);
  const [includeAppendix, setIncludeAppendix] = useState(false);
  const [slideModeChoices, setSlideModeChoices] = useState([
    { id: 'auto', label: 'Auto (dynamic)' },
    { id: 'fixed', label: 'Fixed (always include all core slides)' },
  ]);
  const [templateChoices, setTemplateChoices] = useState([
    { id: 'corporate', label: 'Corporate Blue' },
    { id: 'ocean', label: 'Ocean Teal' },
    { id: 'sunrise', label: 'Sunrise Amber' },
  ]);

  const currentYear = new Date().getFullYear();
  const years = [currentYear - 2, currentYear - 1, currentYear];
  const featureCards = [
    {
      title: 'Executive Summary',
      description: 'High-level overview of key findings and trends',
      icon: FileText,
    },
    {
      title: 'Theme Analysis',
      description: 'Top governance themes ranked by mention count',
      icon: BarChart3,
    },
    {
      title: 'Sentiment Breakdown',
      description: 'Positive, neutral, and negative sentiment percentages',
      icon: Smile,
    },
    {
      title: 'Anomaly Detection',
      description: 'Critical deviations flagged for review',
      icon: TriangleAlert,
    },
    {
      title: 'AI Recommendations',
      description: 'Actionable insights based on data analysis',
      icon: Sparkles,
    },
    {
      title: 'HTML Export',
      description: 'Download formatted reports for sharing and printing',
      icon: Download,
    },
  ];

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const yearFromQuery = parseInt(params.get('year'), 10);
    if (Number.isFinite(yearFromQuery)) {
      setSelectedYear(yearFromQuery);
    }
  }, [location.search]);

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const response = await reportsAPI.getPresentationTemplates();
        const templates = response?.data?.templates;
        const modes = response?.data?.slide_modes;
        if (Array.isArray(templates) && templates.length > 0) {
          setTemplateChoices(templates);
          if (!templates.find((item) => item.id === templateTheme)) {
            setTemplateTheme(templates[0].id);
          }
        }
        if (Array.isArray(modes) && modes.length > 0) {
          setSlideModeChoices(modes);
          if (!modes.find((item) => item.id === slideMode)) {
            setSlideMode(modes[0].id);
          }
        }
      } catch (error) {
        console.warn('Falling back to local template list:', error);
      }
    };

    loadTemplates();
  }, [templateTheme, slideMode]);

  const handleDownloadReport = async () => {
    setDownloading(true);
    try {
      const response = await reportsAPI.getFormattedHtmlReport({ year: selectedYear });
      const data = response.data;
      const html = data.html;
      
      // Create and trigger download
      const element = document.createElement('a');
      element.setAttribute('href', 'data:text/html;charset=utf-8,' + encodeURIComponent(html));
      element.setAttribute('download', `governance-report-${selectedYear}.html`);
      element.style.display = 'none';
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
      
      notifySuccess('Report downloaded successfully');
    } catch (error) {
      console.error('Download error:', error);
      notifyError('Failed to download report');
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadPresentation = async () => {
    setPptDownloading(true);
    try {
      const response = await reportsAPI.exportPresentation({
        year: selectedYear,
        template_theme: templateTheme,
        top_n_themes: topNThemes,
        slide_mode: slideMode,
        include_anomalies: includeAnomalies,
        include_speaker_notes: includeSpeakerNotes,
        include_appendix: includeAppendix,
      });

      const blob = new Blob([
        response.data,
      ], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeTheme = templateTheme || 'corporate';
      link.href = url;
      link.download = `governance-presentation-${selectedYear}-${safeTheme}.pptx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      notifySuccess('Presentation downloaded successfully');
      setShowPptModal(false);
    } catch (error) {
      console.error('PPTX export error:', error);
      notifyError('Failed to export presentation');
    } finally {
      setPptDownloading(false);
    }
  };

  return (
    <div className="reports-page">
      <div className="reports-header">
        <div className="reports-header-content">
          <h1 className="reports-title">
            <TrendingUp size={32} />
            Governance Reports
          </h1>
          <p className="reports-subtitle">View AI-generated insights and downloadable summaries for your organization</p>
        </div>
      </div>

      <div className="reports-container">
        {/* Year Selector & Download */}
        <div className="reports-controls">
          <div className="reports-control-group">
            <label className="reports-control-label">
              <Calendar size={16} />
              Select Year
            </label>
            <select
              className="reports-year-select"
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value))}
            >
              {years.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </div>
          <div className="reports-export-actions">
            <button
              className="reports-download-btn"
              onClick={handleDownloadReport}
              disabled={downloading}
            >
              <Download size={16} />
              {downloading ? 'Downloading...' : 'Download Full Report'}
            </button>
            <button
              className="reports-download-btn reports-ppt-btn"
              onClick={() => setShowPptModal(true)}
              disabled={pptDownloading}
            >
              <Download size={16} />
              {pptDownloading ? 'Preparing...' : 'Export Presentation (PPTX)'}
            </button>
          </div>
        </div>

        {showPptModal && (
          <div className="reports-modal-overlay" role="dialog" aria-modal="true" aria-label="Presentation export options" onClick={() => setShowPptModal(false)}>
            <div className="reports-modal-card" onClick={(e) => e.stopPropagation()}>
              <h3>Presentation Export Options</h3>
              <p className="reports-modal-subtitle">Choose your template theme and content settings.</p>

              <div className="reports-modal-field">
                <label htmlFor="ppt-template-theme">Template Theme</label>
                <select
                  id="ppt-template-theme"
                  value={templateTheme}
                  onChange={(e) => setTemplateTheme(e.target.value)}
                >
                  {templateChoices.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </div>

              <div className="reports-modal-field">
                <label htmlFor="ppt-slide-mode">Slide Strategy</label>
                <select
                  id="ppt-slide-mode"
                  value={slideMode}
                  onChange={(e) => setSlideMode(e.target.value)}
                >
                  {slideModeChoices.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </div>

              <div className="reports-modal-field">
                <label htmlFor="ppt-top-themes">Top Themes Count</label>
                <input
                  id="ppt-top-themes"
                  type="number"
                  min="3"
                  max="10"
                  value={topNThemes}
                  onChange={(e) => setTopNThemes(Math.max(3, Math.min(10, parseInt(e.target.value, 10) || 6)))}
                />
              </div>

              <label className="reports-modal-check">
                <input
                  type="checkbox"
                  checked={includeAnomalies}
                  onChange={(e) => setIncludeAnomalies(e.target.checked)}
                />
                Include anomaly slide details
              </label>

              <label className="reports-modal-check">
                <input
                  type="checkbox"
                  checked={includeSpeakerNotes}
                  onChange={(e) => setIncludeSpeakerNotes(e.target.checked)}
                />
                Include speaker notes on slides
              </label>

              <label className="reports-modal-check">
                <input
                  type="checkbox"
                  checked={includeAppendix}
                  onChange={(e) => setIncludeAppendix(e.target.checked)}
                />
                Include appendix (data quality and scope)
              </label>

              <div className="reports-modal-actions">
                <button className="reports-modal-cancel" onClick={() => setShowPptModal(false)} disabled={pptDownloading}>
                  Cancel
                </button>
                <button className="reports-modal-submit" onClick={handleDownloadPresentation} disabled={pptDownloading}>
                  {pptDownloading ? 'Generating...' : 'Download PPTX'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Executive Summary Card */}
        <div className="reports-content">
          <ExecutiveSummaryCard year={selectedYear} />
        </div>

        {/* Additional Report Options */}
        <div className="reports-options">
          <div className="reports-option-card">
            <div className="reports-option-icon">📧</div>
            <h3>Email Scheduled Reports</h3>
            <p>Configure automatic weekly, monthly, or daily report delivery to your inbox.</p>
            <Link to={{ pathname: '/settings', hash: '#report-schedule-settings' }} className="reports-option-link">
              Go to Settings →
            </Link>
          </div>

          <div className="reports-option-card">
            <div className="reports-option-icon">📊</div>
            <h3>Interactive Dashboard</h3>
            <p>Explore real-time trends, themes, and sentiment analysis in the Trends Dashboard.</p>
            <Link to="/trend-analysis" className="reports-option-link">
              Open Dashboard →
            </Link>
          </div>

          <div className="reports-option-card">
            <div className="reports-option-icon">🔍</div>
            <h3>Search & Export</h3>
            <p>Search meetings, export raw data, and perform custom analysis on governance records.</p>
            <Link to="/search" className="reports-option-link">
              Search Data →
            </Link>
          </div>
        </div>

        {/* Report Features */}
        <div className="reports-features">
          <div className="reports-features-header">
            <h2>Report Features</h2>
            <p>Everything included in the analytics view, arranged by the core reporting workflow.</p>
          </div>
          <div className="reports-features-grid">
            {featureCards.map(({ title, description, icon: Icon }) => (
              <div className="reports-feature" key={title}>
                <div className="reports-feature-icon" aria-hidden="true">
                  <Icon size={22} strokeWidth={2.2} />
                </div>
                <h4>{title}</h4>
                <p>{description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReportsPage;
