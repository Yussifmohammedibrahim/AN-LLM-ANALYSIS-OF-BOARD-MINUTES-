import React, { useState, useEffect, useCallback } from 'react';
import { TrendingUp, AlertCircle, Lightbulb, Plus, Minus, RefreshCw, Presentation } from 'lucide-react';
import api from '../api/api';
import { notifyError } from '../utils/notify';
import EnhancedPresentationModal from './EnhancedPresentationModal';
import './ExecutiveSummaryCard.css';

const ExecutiveSummaryCard = ({ year = null }) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showEnhancedModal, setShowEnhancedModal] = useState(false);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const params = year ? `?year=${year}` : '';
      const response = await api.get(`/api/reports/executive-summary${params}`);
      setSummary(response.data);
    } catch (error) {
      console.warn('Failed to load executive summary:', error);
      notifyError('Could not load summary');
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => {
    loadSummary();
  }, [year, loadSummary]);

  const downloadReport = async () => {
    try {
      const params = year ? `?year=${year}` : '';
      const response = await api.get(`/api/reports/formatted-html${params}`);
      const html = response.data.html;
      
      // Create downloadable HTML file
      const element = document.createElement('a');
      element.setAttribute('href', 'data:text/html;charset=utf-8,' + encodeURIComponent(html));
      element.setAttribute('download', `governance-report-${year || new Date().getFullYear()}.html`);
      element.style.display = 'none';
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
    } catch (error) {
      notifyError('Failed to download report');
    }
  };

  if (loading) {
    return (
      <div className="exec-summary-card loading">
        <div className="exec-summary-skeleton" />
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  const stats = summary.statistics || {};
  const resolveThemeLabel = (theme) => {
    const primary = String(theme?.theme || theme?.name || '').trim();
    // Filter out common noise words, titles, and generic labels
    const isNoise = /^(the|the\s+of|mr|dr|lecturer|chairman|department|student|students|meetings?|discussion|topic|themes?|unknown)$/i.test(primary);
    
    if (primary && !isNoise && !/^unknown( theme)?$/i.test(primary) && !/^theme(s)?$/i.test(primary) && !/^topic$/i.test(primary)) return primary;

    const keyword = Array.isArray(theme?.keywords) && theme.keywords.length > 0
      ? theme.keywords.map((item) => String(item || '').trim()).filter(Boolean).slice(0, 4).join(' ')
      : '';
    if (keyword && !/^theme(s)?$/i.test(keyword) && !/^topic$/i.test(keyword)) return keyword;

    return String(theme?.theme_id || 'Cluster').trim();
  };

  return (
    <div className="exec-summary-card">
      <div className="exec-summary-header">
        <div className="exec-summary-title-section">
          <TrendingUp size={24} className="exec-summary-icon" />
          <div>
            <h3 className="exec-summary-title">Executive Summary</h3>
            <p className="exec-summary-subtitle">{summary.year} Governance Report</p>
          </div>
        </div>
        <div className="exec-summary-header-buttons">
          <button
            className="exec-summary-expand-btn"
            onClick={() => setExpanded(!expanded)}
            title={expanded ? 'Collapse' : 'Expand'}
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse executive summary' : 'Expand executive summary'}
          >
            {expanded ? <Minus size={20} /> : <Plus size={20} />}
          </button>
          <button
            className="exec-summary-expand-btn"
            onClick={loadSummary}
            title="Refresh summary data"
            aria-label="Refresh executive summary"
            disabled={loading}
          >
            <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="exec-summary-body">
        <p className="exec-summary-text">{summary.executive_summary}</p>

        {expanded && (
          <div className="exec-summary-expanded">
            {/* Statistics Grid */}
            <div className="exec-summary-stats">
              <div className="exec-stat">
                <div className="exec-stat-label">Meetings</div>
                <div className="exec-stat-value">{stats.total_meetings || 0}</div>
              </div>
              <div className="exec-stat">
                <div className="exec-stat-label">Themes</div>
                <div className="exec-stat-value">{stats.total_themes || 0}</div>
              </div>
              <div className="exec-stat">
                <div className="exec-stat-label">Sentiment</div>
                <div className="exec-stat-value" style={{ textTransform: 'capitalize' }}>
                  {stats.sentiment_trend || 'Unknown'}
                </div>
              </div>
              <div className="exec-stat">
                <div className="exec-stat-label">Anomalies</div>
                <div className="exec-stat-value" style={{ color: stats.critical_anomalies > 0 ? '#ef4444' : '#10b981' }}>
                  {stats.critical_anomalies || 0}
                </div>
              </div>
            </div>

            {/* Top Themes */}
            {summary.top_themes && summary.top_themes.length > 0 && (
              <div className="exec-summary-section">
                <h4 className="exec-summary-section-title">Top Themes</h4>
                <div className="exec-summary-theme-list">
                  {summary.top_themes.map((theme, idx) => (
                    <div key={idx} className="exec-theme-item">
                      <div className="exec-theme-name">{resolveThemeLabel(theme)}</div>
                      <div className="exec-theme-bar">
                        <div
                          className="exec-theme-bar-fill"
                          style={{ width: `${theme.percentage}%` }}
                        />
                      </div>
                      <div className="exec-theme-detail">
                        {theme.mentions} mentions • {theme.percentage}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Sentiment Breakdown */}
            {summary.sentiment && (
              <div className="exec-summary-section">
                <h4 className="exec-summary-section-title">Sentiment Breakdown</h4>
                <div className="exec-sentiment-bars">
                  <div className="exec-sentiment-bar">
                    <div className="exec-sentiment-label">Positive</div>
                    <div className="exec-sentiment-progress">
                      <div
                        className="exec-sentiment-progress-fill positive"
                        style={{ width: `${summary.sentiment.positive_rate}%` }}
                      />
                    </div>
                    <div className="exec-sentiment-percent">{summary.sentiment.positive_rate}%</div>
                  </div>
                  <div className="exec-sentiment-bar">
                    <div className="exec-sentiment-label">Neutral</div>
                    <div className="exec-sentiment-progress">
                      <div
                        className="exec-sentiment-progress-fill neutral"
                        style={{ width: `${summary.sentiment.neutral_rate}%` }}
                      />
                    </div>
                    <div className="exec-sentiment-percent">{summary.sentiment.neutral_rate}%</div>
                  </div>
                  <div className="exec-sentiment-bar">
                    <div className="exec-sentiment-label">Negative</div>
                    <div className="exec-sentiment-progress">
                      <div
                        className="exec-sentiment-progress-fill negative"
                        style={{ width: `${summary.sentiment.negative_rate}%` }}
                      />
                    </div>
                    <div className="exec-sentiment-percent">{summary.sentiment.negative_rate}%</div>
                  </div>
                </div>
              </div>
            )}

            {/* Critical Anomalies */}
            {summary.critical_anomalies && summary.critical_anomalies.length > 0 && (
              <div className="exec-summary-section">
                <h4 className="exec-summary-section-title">
                  <AlertCircle size={16} style={{ marginRight: '8px' }} />
                  Critical Anomalies
                </h4>
                <div className="exec-anomaly-list">
                  {summary.critical_anomalies.slice(0, 3).map((anomaly, idx) => (
                    <div key={idx} className="exec-anomaly-item">
                      <div className="exec-anomaly-theme">{anomaly.theme}</div>
                      <div className="exec-anomaly-detail">
                        {anomaly.month} • {anomaly.mentions} mentions (baseline: {anomaly.baseline})
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendations */}
            {summary.recommendations && summary.recommendations.length > 0 && (
              <div className="exec-summary-section">
                <h4 className="exec-summary-section-title">
                  <Lightbulb size={16} style={{ marginRight: '8px' }} />
                  AI Recommendations
                </h4>
                <div className="exec-recommendation-list">
                  {summary.recommendations.map((rec, idx) => (
                    <div key={idx} className="exec-recommendation-item">
                      {rec}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="exec-summary-buttons-container">
              <div className="exec-summary-actions-row">
                <button className="exec-summary-download-btn" onClick={downloadReport}>
                  📥 Download Full Report (HTML)
                </button>
                <button className="exec-summary-download-btn exec-summary-ppt-btn" onClick={() => setShowEnhancedModal(true)}>
                  <Presentation size={16} style={{ marginRight: '6px' }} />
                  Advanced Export
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Enhanced Presentation Modal */}
      {showEnhancedModal && (
        <EnhancedPresentationModal
          year={year}
          onClose={() => setShowEnhancedModal(false)}
        />
      )}
    </div>
  );
};

export default ExecutiveSummaryCard;
