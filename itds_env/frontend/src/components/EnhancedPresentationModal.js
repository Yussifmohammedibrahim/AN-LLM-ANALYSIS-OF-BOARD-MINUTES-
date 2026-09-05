import React, { useState } from 'react';
import {
  Download,
  Package,
  Zap,
  Share2,
  BarChart3,
  Palette,
  Clock,
} from 'lucide-react';
import { reportsAPI } from '../api/api';
import { notifySuccess, notifyError } from '../utils/notify';
import './EnhancedPresentationModal.css';

/**
 * Enhanced Presentation Export Modal
 * Supports all 8 enhancement categories:
 * 1. Data Visualizations
 * 2. Branding & Customization
 * 3. Content Organization
 * 4. Interactive Features
 * 5. Advanced Analytics
 * 6. Distribution & Scheduling
 * 7. Export Variants
 * 8. Visual Enhancements
 */

const EnhancedPresentationModal = ({ year = 2026, onClose = () => {} }) => {
  const [activeTab, setActiveTab] = useState('basic');
  const [downloading, setDownloading] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Tab 1: Basic Options
  const [templateTheme, setTemplateTheme] = useState('corporate');
  const [slideMode, setSlideMode] = useState('auto');
  const [exportFormat, setExportFormat] = useState('pptx');

  // Tab 2: Branding
  const [orgName, setOrgName] = useState('');
  const [logoUrl, setLogoUrl] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#667eea');
  const [watermark, setWatermark] = useState('');
  const [footerText, setFooterText] = useState('');

  // Tab 3: Content
  const [includeTOC, setIncludeTOC] = useState(true);
  const [includeTables, setIncludeTables] = useState(true);
  const [includeAppendix, setIncludeAppendix] = useState(false);
  const [includeNotes, setIncludeNotes] = useState(true);
  const [includeQR, setIncludeQR] = useState(false);

  // Tab 4: Advanced Analytics
  const [includeSentimentTrends, setIncludeSentimentTrends] = useState(true);
  const [includeGrowthAnalysis, setIncludeGrowthAnalysis] = useState(true);
  const [includeAnomalyDetails, setIncludeAnomalyDetails] = useState(true);
  const [includePrioritizedRecs, setIncludePrioritizedRecs] = useState(true);
  const [includeKeyMetrics, setIncludeKeyMetrics] = useState(true);

  // Tab 5: Distribution
  const [scheduleFrequency, setScheduleFrequency] = useState('once');
  const [emailRecipients, setEmailRecipients] = useState('');
  const [scheduleTime, setScheduleTime] = useState('09:00');

  // Tab 6: Visual Enhancements
  const [includeBackgroundGradient, setIncludeBackgroundGradient] = useState(true);
  const [highContrast, setHighContrast] = useState(false);
  const [enableTransitions, setEnableTransitions] = useState(false);

  const themes = [
    { id: 'corporate', label: '🏢 Corporate Blue' },
    { id: 'ocean', label: '🌊 Ocean Teal' },
    { id: 'sunrise', label: '🌅 Sunrise Amber' },
  ];

  const slideModes = [
    { id: 'auto', label: 'Auto (adapt to data)' },
    { id: 'fixed', label: 'Fixed (6 slides)' },
    { id: 'minimal', label: 'Minimal (3 slides)' },
  ];

  const exportFormats = [
    { id: 'pptx', label: '📊 PowerPoint (.pptx)' },
    { id: 'pdf', label: '📄 PDF Document' },
    { id: 'handout', label: '📑 Handout (4/page)' },
    { id: 'html', label: '🌐 Web Format (HTML)' },
  ];

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const payload = {
        year,
        template_theme: templateTheme,
        slide_mode: slideMode,
        export_format: exportFormat,
        include_speaker_notes: includeNotes,
        include_anomalies: includeAnomalyDetails,

        // Branding
        organization_name: orgName,
        logo_url: logoUrl,
        primary_color: primaryColor,
        watermark,
        footer_text: footerText,

        // Content
        include_toc: includeTOC,
        include_tables: includeTables,
        include_appendix: includeAppendix,
        include_qr_code: includeQR,

        // Advanced Analytics
        include_sentiment_trends: includeSentimentTrends,
        include_growth_analysis: includeGrowthAnalysis,
        include_key_metrics_callout: includeKeyMetrics,
        include_prioritized_recommendations: includePrioritizedRecs,

        // Visual
        include_background_gradient: includeBackgroundGradient,
        high_contrast_mode: highContrast,
        enable_transitions: enableTransitions,
      };

      const response = await reportsAPI.exportPresentationEnhanced(payload);

      // Determine file extension
      const ext = exportFormat === 'pptx' ? 'pptx' : exportFormat === 'pdf' ? 'pdf' : 'html';
      const filename = `governance-presentation-${year}-${templateTheme}.${ext}`;

      // Download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      notifySuccess('Presentation exported successfully!');
      onClose();
    } catch (error) {
      console.error('Export error:', error);
      notifyError('Failed to export presentation');
    } finally {
      setDownloading(false);
    }
  };

  const handleScheduleReport = async () => {
    if (!emailRecipients.trim()) {
      notifyError('Please enter at least one email recipient');
      return;
    }

    setExporting(true);
    try {
      await reportsAPI.scheduleReport({
        year,
        template_theme: templateTheme,
        frequency: scheduleFrequency,
        email_recipients: emailRecipients.split(',').map(e => e.trim()),
        send_time: scheduleTime,
        include_anomalies: includeAnomalyDetails,
        include_notes: includeNotes,
      });

      notifySuccess('Report scheduled successfully!');
      onClose();
    } catch (error) {
      console.error('Schedule error:', error);
      notifyError('Failed to schedule report');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="enhanced-modal-overlay" onClick={onClose}>
      <div className="enhanced-modal" onClick={(e) => e.stopPropagation()}>
        <div className="enhanced-modal-header">
          <h2>🎨 Enhanced Presentation Export</h2>
          <button className="enhanced-modal-close" onClick={onClose}>×</button>
        </div>

        {/* Tab Navigation */}
        <div className="enhanced-modal-tabs">
          <button
            className={`tab-btn ${activeTab === 'basic' ? 'active' : ''}`}
            onClick={() => setActiveTab('basic')}
          >
            <Download size={16} /> Basic
          </button>
          <button
            className={`tab-btn ${activeTab === 'branding' ? 'active' : ''}`}
            onClick={() => setActiveTab('branding')}
          >
            <Palette size={16} /> Branding
          </button>
          <button
            className={`tab-btn ${activeTab === 'content' ? 'active' : ''}`}
            onClick={() => setActiveTab('content')}
          >
            <Package size={16} /> Content
          </button>
          <button
            className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
            onClick={() => setActiveTab('analytics')}
          >
            <BarChart3 size={16} /> Analytics
          </button>
          <button
            className={`tab-btn ${activeTab === 'distribution' ? 'active' : ''}`}
            onClick={() => setActiveTab('distribution')}
          >
            <Share2 size={16} /> Distribution
          </button>
          <button
            className={`tab-btn ${activeTab === 'visual' ? 'active' : ''}`}
            onClick={() => setActiveTab('visual')}
          >
            <Zap size={16} /> Visual
          </button>
        </div>

        {/* Tab Content */}
        <div className="enhanced-modal-content">
          {/* Basic Tab */}
          {activeTab === 'basic' && (
            <div className="tab-content">
              <h3>Basic Export Options</h3>

              <div className="form-group">
                <label>Template Theme</label>
                <select value={templateTheme} onChange={(e) => setTemplateTheme(e.target.value)}>
                  {themes.map(t => (
                    <option key={t.id} value={t.id}>{t.label}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Export Format</label>
                <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}>
                  {exportFormats.map(f => (
                    <option key={f.id} value={f.id}>{f.label}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Slide Mode</label>
                <select value={slideMode} onChange={(e) => setSlideMode(e.target.value)}>
                  {slideModes.map(m => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Branding Tab */}
          {activeTab === 'branding' && (
            <div className="tab-content">
              <h3>Organization Branding</h3>

              <div className="form-group">
                <label>Organization Name</label>
                <input
                  type="text"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="e.g., Acme Corp"
                />
              </div>

              <div className="form-group">
                <label>Logo URL</label>
                <input
                  type="url"
                  value={logoUrl}
                  onChange={(e) => setLogoUrl(e.target.value)}
                  placeholder="https://example.com/logo.png"
                />
              </div>

              <div className="form-group">
                <label>Primary Brand Color</label>
                <div className="color-input-group">
                  <input
                    type="color"
                    value={primaryColor}
                    onChange={(e) => setPrimaryColor(e.target.value)}
                  />
                  <input
                    type="text"
                    value={primaryColor}
                    onChange={(e) => setPrimaryColor(e.target.value)}
                    placeholder="#667eea"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Watermark</label>
                <select value={watermark} onChange={(e) => setWatermark(e.target.value)}>
                  <option value="">None</option>
                  <option value="DRAFT">Draft</option>
                  <option value="CONFIDENTIAL">Confidential</option>
                  <option value="INTERNAL">Internal Use Only</option>
                  <option value="EXTERNAL">External</option>
                </select>
              </div>

              <div className="form-group">
                <label>Footer Text</label>
                <input
                  type="text"
                  value={footerText}
                  onChange={(e) => setFooterText(e.target.value)}
                  placeholder="e.g., Company Confidential"
                />
              </div>
            </div>
          )}

          {/* Content Tab */}
          {activeTab === 'content' && (
            <div className="tab-content">
              <h3>Content Organization</h3>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeTOC}
                    onChange={(e) => setIncludeTOC(e.target.checked)}
                  />
                  Include Table of Contents
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeTables}
                    onChange={(e) => setIncludeTables(e.target.checked)}
                  />
                  Include Data Tables
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeAppendix}
                    onChange={(e) => setIncludeAppendix(e.target.checked)}
                  />
                  Include Appendix (methodology, glossary)
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeNotes}
                    onChange={(e) => setIncludeNotes(e.target.checked)}
                  />
                  Include Speaker Notes
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeQR}
                    onChange={(e) => setIncludeQR(e.target.checked)}
                  />
                  Include QR Code (link to dashboard)
                </label>
              </div>
            </div>
          )}

          {/* Analytics Tab */}
          {activeTab === 'analytics' && (
            <div className="tab-content">
              <h3>Advanced Analytics</h3>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeKeyMetrics}
                    onChange={(e) => setIncludeKeyMetrics(e.target.checked)}
                  />
                  Key Metrics Snapshot (visual callout)
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeSentimentTrends}
                    onChange={(e) => setIncludeSentimentTrends(e.target.checked)}
                  />
                  Sentiment Trend Chart (12-month)
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeGrowthAnalysis}
                    onChange={(e) => setIncludeGrowthAnalysis(e.target.checked)}
                  />
                  Growth Analysis (YoY comparison)
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeAnomalyDetails}
                    onChange={(e) => setIncludeAnomalyDetails(e.target.checked)}
                  />
                  Detailed Anomaly Table
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includePrioritizedRecs}
                    onChange={(e) => setIncludePrioritizedRecs(e.target.checked)}
                  />
                  Prioritized Recommendations (with badges)
                </label>
              </div>
            </div>
          )}

          {/* Distribution Tab */}
          {activeTab === 'distribution' && (
            <div className="tab-content">
              <h3>Schedule & Distribution</h3>

              <div className="form-group">
                <label>Frequency</label>
                <select value={scheduleFrequency} onChange={(e) => setScheduleFrequency(e.target.value)}>
                  <option value="once">Export Now</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>

              {scheduleFrequency !== 'once' && (
                <div className="form-group">
                  <label>Send Time</label>
                  <input
                    type="time"
                    value={scheduleTime}
                    onChange={(e) => setScheduleTime(e.target.value)}
                  />
                </div>
              )}

              <div className="form-group">
                <label>Email Recipients (comma-separated)</label>
                <textarea
                  value={emailRecipients}
                  onChange={(e) => setEmailRecipients(e.target.value)}
                  placeholder="user@example.com, another@example.com"
                  rows="3"
                />
              </div>

              <div className="info-box">
                <p>💡 Scheduled reports will be automatically generated and sent at the specified time.</p>
              </div>
            </div>
          )}

          {/* Visual Tab */}
          {activeTab === 'visual' && (
            <div className="tab-content">
              <h3>Visual Enhancements</h3>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={includeBackgroundGradient}
                    onChange={(e) => setIncludeBackgroundGradient(e.target.checked)}
                  />
                  Include Background Gradients
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={highContrast}
                    onChange={(e) => setHighContrast(e.target.checked)}
                  />
                  High Contrast Mode (accessibility)
                </label>
              </div>

              <div className="checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={enableTransitions}
                    onChange={(e) => setEnableTransitions(e.target.checked)}
                  />
                  Enable Slide Transitions (PDF/HTML)
                </label>
              </div>

              <div className="info-box">
                <p>📊 These settings enhance visual presentation while maintaining professional appearance.</p>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="enhanced-modal-actions">
          <button
            className="btn-secondary"
            onClick={onClose}
          >
            Cancel
          </button>

          {scheduleFrequency !== 'once' ? (
            <button
              className="btn-primary"
              onClick={handleScheduleReport}
              disabled={exporting || !emailRecipients.trim()}
            >
              <Clock size={16} />
              {exporting ? 'Scheduling...' : 'Schedule Report'}
            </button>
          ) : (
            <button
              className="btn-primary"
              onClick={handleDownload}
              disabled={downloading}
            >
              <Download size={16} />
              {downloading ? 'Exporting...' : 'Export Presentation'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default EnhancedPresentationModal;
