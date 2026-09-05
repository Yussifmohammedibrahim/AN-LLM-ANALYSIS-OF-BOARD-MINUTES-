import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  LockKeyhole,
  Search,
  ShieldCheck,
  Upload,
  TrendingUp,
  Mic,
  FileSpreadsheet,
  Layers,
  Activity,
  Cpu,
  ChevronDown,
  ChevronUp,
  Clock,
  Sparkles,
  Database,
  AlertTriangle,
  ArrowUpRight,
  Users,
  Terminal,
  Calendar,
  Check,
  Menu,
  X
} from 'lucide-react';
import './LandingPage.css';

const capabilities = [
  {
    icon: FileText,
    badge: 'Multi-Modal Ingestion',
    title: 'Comprehensive Document & Audio Intake',
    description:
      'Ingest multi-hundred-page board packs, scanned committee PDFs, DOCX minutes, and raw boardroom audio recordings into one unified, indexed intelligence repository.',
    linkText: 'Explore Ingestion Pipeline',
  },
  {
    icon: Cpu,
    badge: 'LLM Intelligence',
    title: 'Context-Aware Executive Synthesis',
    description:
      'Generate verifiable, citation-backed executive digests. Extract formal resolutions, risk disclosures, and committee action items with zero hallucinations.',
    linkText: 'Learn About LLM Models',
  },
  {
    icon: TrendingUp,
    badge: 'Longitudinal Trends',
    title: 'Cross-Meeting Anomaly & Trend Radar',
    description:
      'Track strategic themes across quarters and fiscal years. Automatically surface statistical anomalies, sudden topic shifts, and unaddressed governance risks.',
    linkText: 'View Trend Analytics',
  },
  {
    icon: Mic,
    badge: 'Voice Diarization',
    title: 'Speaker Diarization & Audio Analysis',
    description:
      'Transcribe boardroom deliberations with high-precision speaker separation. Map spoken commitments directly to written action items and minutes.',
    linkText: 'See Voice Capabilities',
  },
  {
    icon: FileSpreadsheet,
    badge: 'Executive Export',
    title: 'Automated PPTX & Committee Briefings',
    description:
      'Export boardroom-ready PowerPoint presentation decks and executive PDF reports with one click, formatted to strict corporate governance standards.',
    linkText: 'Review Export Formats',
  },
  {
    icon: ShieldCheck,
    badge: 'Enterprise Security',
    title: 'Granular RBAC & Immutable Audit Trails',
    description:
      'Protect confidential board matters with multi-tiered role permissions (Super Admin, Admin, Editor, Viewer), SHA-256 document hashing, and tamper-evident logs.',
    linkText: 'Audit Architecture',
  },
];

const faqs = [
  {
    q: 'How does the platform safeguard confidential boardroom discussions?',
    a: 'Security is paramount. The platform enforces AES-256 encryption at rest and TLS 1.3 in transit. Enterprise deployments support private VPC or air-gapped on-premise configurations. We enforce strict zero-data-retention AI processing so proprietary board records are never used to train third-party models.',
  },
  {
    q: 'Can the system process audio recordings from live board meetings?',
    a: 'Yes. Our multi-modal engine ingests standard audio formats (WAV, MP3, M4A) and applies advanced acoustic models with speaker diarization. It separates individual speakers (Chair, CFO, Legal Counsel) and maps verbal commitments directly to formal meeting actions.',
  },
  {
    q: 'How does the platform prevent LLM hallucinations in executive summaries?',
    a: 'Every extracted theme, resolution, and action item is tied via cryptographic character-offset citations to the exact source paragraph in the original board pack or audio timestamp. Directors and counsel can click any summary line to inspect the original text immediately.',
  },
  {
    q: 'What role-based access control (RBAC) levels are supported?',
    a: 'We provide four enterprise tiers: Super Admin (system configuration & global audit), Admin (user management & workspace governance), Editor (document upload, transcription & report editing), and Viewer (read-only access to published board digests & dashboards).',
  },
  {
    q: 'Can automated reports and PowerPoint presentations be scheduled?',
    a: 'Yes. The system includes an automated scheduling engine that dispatches consolidated governance summaries, trend reports, and presentation-ready PPTX decks to committee members on daily, weekly, or post-meeting cadences.',
  },
];

const LandingPage = () => {
  const [activeTab, setActiveTab] = useState('executive');
  const [openFaq, setOpenFaq] = useState(0);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="landing-enterprise">
      {/* Clean Enterprise Navigation */}
      <header className="ent-nav">
        <div className="ent-nav-inner">
          <Link to="/" className="ent-brand" aria-label="Board Minutes Platform">
            <div className="ent-brand-logo-wrap">
              <img src="/ITDS_LOGO.png" alt="ITDS Logo" className="ent-brand-logo" />
            </div>
            <span className="ent-brand-title">BOARD MINUTES</span>
          </Link>

          <nav className="ent-nav-menu" aria-label="Primary Navigation">
            <a href="#capabilities" className="ent-nav-link">Capabilities</a>
            <a href="#workflow" className="ent-nav-link">Workflow</a>
            <a href="#security" className="ent-nav-link">Security</a>
            <a href="#faq" className="ent-nav-link">FAQ</a>
          </nav>

          <div className="ent-nav-right">
            <Link to="/login" className="ent-btn-primary ent-nav-btn">
              Sign In <ArrowRight size={15} />
            </Link>
            <button
              type="button"
              className="ent-mobile-toggle"
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
              aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
            >
              {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Dropdown */}
        {mobileNavOpen && (
          <div className="ent-mobile-menu">
            <a href="#capabilities" className="ent-mobile-link" onClick={() => setMobileNavOpen(false)}>Capabilities</a>
            <a href="#workflow" className="ent-mobile-link" onClick={() => setMobileNavOpen(false)}>Workflow</a>
            <a href="#security" className="ent-mobile-link" onClick={() => setMobileNavOpen(false)}>Security</a>
            <a href="#faq" className="ent-mobile-link" onClick={() => setMobileNavOpen(false)}>FAQ</a>
            <Link to="/login" className="ent-btn-primary ent-mobile-signin" onClick={() => setMobileNavOpen(false)}>
              Sign In <ArrowRight size={15} />
            </Link>
          </div>
        )}
      </header>

      <main id="top">
        {/* Hero Section */}
        <section className="ent-hero">
          <div className="ent-hero-bg-glow" />
          <div className="ent-hero-grid-pattern" />

          <div className="ent-container ent-hero-container">
            <div className="ent-hero-content">
              <div className="ent-pill-tag">
                <Sparkles size={14} className="ent-sparkle-icon" />
                <span>Next-Gen Governance Intelligence</span>
                <span className="ent-pill-divider" />
                <span className="ent-pill-sub">LLM-Powered Board Analytics</span>
              </div>

              <h1 className="ent-hero-title">
                Bring rigor, speed, and clarity to every{' '}
                <span className="ent-gradient-text">boardroom decision.</span>
              </h1>

              <p className="ent-hero-description">
                The standard enterprise workspace for Corporate Secretaries, General Counsels, and Board Directors.
                Ingest multi-modal meeting minutes and audio, generate citation-backed executive briefings, track multi-quarter compliance trends, and export committee-ready PPTX decks.
              </p>

              <div className="ent-hero-cta-group">
                <Link to="/login" className="ent-btn-primary ent-btn-hero">
                  Enter Board Workspace <ArrowRight size={18} />
                </Link>
                <a href="#console" className="ent-btn-secondary ent-btn-hero">
                  <Terminal size={17} /> Explore Interactive Console
                </a>
              </div>

              <div className="ent-hero-trust-row">
                <div className="ent-trust-item">
                  <ShieldCheck size={16} className="ent-trust-icon" />
                  <span>256-bit Bank-Grade Encryption</span>
                </div>
                <div className="ent-trust-sep" />
                <div className="ent-trust-item">
                  <LockKeyhole size={16} className="ent-trust-icon" />
                  <span>Strict Zero-Data Retention Option</span>
                </div>
                <div className="ent-trust-sep" />
                <div className="ent-trust-item">
                  <CheckCircle2 size={16} className="ent-trust-icon" />
                  <span>Immutable Audit Logging</span>
                </div>
              </div>
            </div>

            {/* Hero Quick KPI Preview Banner */}
            <div className="ent-hero-kpi-grid">
              <div className="ent-kpi-card">
                <div className="ent-kpi-val">78%</div>
                <div className="ent-kpi-label">Reduction in Review Time</div>
                <div className="ent-kpi-sub">Automated 200+ page synthesis</div>
              </div>
              <div className="ent-kpi-card">
                <div className="ent-kpi-val">100%</div>
                <div className="ent-kpi-label">Citation Traceability</div>
                <div className="ent-kpi-sub">Verifiable offsets to original text</div>
              </div>
              <div className="ent-kpi-card">
                <div className="ent-kpi-val">&lt; 800ms</div>
                <div className="ent-kpi-label">Semantic Query Latency</div>
                <div className="ent-kpi-sub">Instant cross-meeting recall</div>
              </div>
              <div className="ent-kpi-card">
                <div className="ent-kpi-val">4 Tiers</div>
                <div className="ent-kpi-label">Enterprise RBAC Hierarchy</div>
                <div className="ent-kpi-sub">Granular governance enforcement</div>
              </div>
            </div>
          </div>
        </section>

        {/* Enterprise Industry Validation Strip */}
        <section className="ent-sectors-strip" aria-label="Target Enterprise Verticals">
          <div className="ent-container ent-sectors-container">
            <span className="ent-sectors-label">ENGINEERED FOR HIGHLY REGULATED GOVERNANCE:</span>
            <div className="ent-sectors-list">
              <span className="ent-sector-badge">Financial Services & Banking</span>
              <span className="ent-sector-dot">•</span>
              <span className="ent-sector-badge">Healthcare & Life Sciences</span>
              <span className="ent-sector-dot">•</span>
              <span className="ent-sector-badge">Energy & Infrastructure</span>
              <span className="ent-sector-dot">•</span>
              <span className="ent-sector-badge">Public Sector & Sovereign Entities</span>
              <span className="ent-sector-dot">•</span>
              <span className="ent-sector-badge">Global Enterprise Tech</span>
            </div>
          </div>
        </section>

        {/* Interactive Product Showcase / Console */}
        <section className="ent-section ent-console-section" id="console">
          <div className="ent-container">
            <div className="ent-section-header text-center">
              <div className="ent-eyebrow">
                <Activity size={14} />
                <span>INTERACTIVE WORKSPACE SIMULATOR</span>
              </div>
              <h2 className="ent-section-title">
                Experience the Enterprise Governance Console
              </h2>
              <p className="ent-section-subtitle">
                Explore how the platform unifies document parsing, multi-quarter trend telemetry, speaker audio diarization, and tamper-evident compliance ledgers.
              </p>
            </div>

            {/* Showcase Container */}
            <div className="ent-console-wrapper">
              {/* Tab Navigation */}
              <div className="ent-console-tabs" role="tablist">
                <button
                  type="button"
                  className={`ent-console-tab ${activeTab === 'executive' ? 'active' : ''}`}
                  onClick={() => setActiveTab('executive')}
                  role="tab"
                  aria-selected={activeTab === 'executive'}
                >
                  <FileText size={17} />
                  <span>Executive Digest & Actions</span>
                </button>
                <button
                  type="button"
                  className={`ent-console-tab ${activeTab === 'trends' ? 'active' : ''}`}
                  onClick={() => setActiveTab('trends')}
                  role="tab"
                  aria-selected={activeTab === 'trends'}
                >
                  <TrendingUp size={17} />
                  <span>Longitudinal Trend Radar</span>
                </button>
                <button
                  type="button"
                  className={`ent-console-tab ${activeTab === 'audio' ? 'active' : ''}`}
                  onClick={() => setActiveTab('audio')}
                  role="tab"
                  aria-selected={activeTab === 'audio'}
                >
                  <Mic size={17} />
                  <span>Voice & Diarization</span>
                </button>
                <button
                  type="button"
                  className={`ent-console-tab ${activeTab === 'audit' ? 'active' : ''}`}
                  onClick={() => setActiveTab('audit')}
                  role="tab"
                  aria-selected={activeTab === 'audit'}
                >
                  <ShieldCheck size={17} />
                  <span>Immutable Audit Ledger</span>
                </button>
              </div>

              {/* Console Window */}
              <div className="ent-console-window">
                <div className="ent-window-chrome">
                  <div className="ent-window-dots">
                    <span className="dot dot-red" />
                    <span className="dot dot-yellow" />
                    <span className="dot dot-green" />
                  </div>
                  <div className="ent-window-address">
                    <LockKeyhole size={12} />
                    <span>https://app.itds-governance.com/workspace/board-minutes/q2-review</span>
                  </div>
                  <div className="ent-window-badge">
                    <span className="pulse-indicator" />
                    <span>Active Session · Encrypted</span>
                  </div>
                </div>

                <div className="ent-window-body">
                  {/* TAB 1: EXECUTIVE DIGEST */}
                  {activeTab === 'executive' && (
                    <div className="ent-tab-view ent-tab-executive">
                      <div className="ent-view-header">
                        <div>
                          <span className="ent-tag-pill">CONFIDENTIAL · BOARD & AUDIT COMMITTEE</span>
                          <h3>Q2 2026 Boardpack Comprehensive Review</h3>
                          <p className="ent-meta-row">
                            <span><Calendar size={13} /> June 14, 2026</span>
                            <span>•</span>
                            <span><Clock size={13} /> 3h 45m Deliberation</span>
                            <span>•</span>
                            <span><Users size={13} /> 12 Board Members Present</span>
                          </p>
                        </div>
                        <div className="ent-view-actions">
                          <Link to="/login" className="ent-btn-small">
                            <FileSpreadsheet size={14} /> Export PPTX
                          </Link>
                          <Link to="/login" className="ent-btn-small ent-btn-small-primary">
                            Full Document <ArrowUpRight size={14} />
                          </Link>
                        </div>
                      </div>

                      <div className="ent-metric-ribbon">
                        <div className="ent-ribbon-stat">
                          <span className="ribbon-label">Materials Analyzed</span>
                          <span className="ribbon-value">28 Documents</span>
                          <span className="ribbon-sub">PDFs, DOCX & Audio</span>
                        </div>
                        <div className="ent-ribbon-stat">
                          <span className="ribbon-label">Formal Resolutions</span>
                          <span className="ribbon-value text-emerald">06 Approved</span>
                          <span className="ribbon-sub">Unanimous voting</span>
                        </div>
                        <div className="ent-ribbon-stat">
                          <span className="ribbon-label">Assigned Action Items</span>
                          <span className="ribbon-value text-blue">14 Tracked</span>
                          <span className="ribbon-sub">Across 4 Committees</span>
                        </div>
                        <div className="ent-ribbon-stat">
                          <span className="ribbon-label">LLM Extraction Confidence</span>
                          <span className="ribbon-value text-cyan">99.4%</span>
                          <span className="ribbon-sub">Zero Hallucination Offset</span>
                        </div>
                      </div>

                      <div className="ent-exec-split">
                        <div className="ent-exec-card">
                          <div className="ent-card-title">
                            <Sparkles size={16} className="text-amber" />
                            <span>Executive Summary & Strategic Decisions</span>
                          </div>
                          <p className="ent-summary-text">
                            The Board formally approved the FY27 Capital Reallocation Strategy ($45M allocation to enterprise cybersecurity & cloud migration). The Audit Committee confirmed completion of the ISO 27001 surveillance audit with zero non-conformities noted.
                          </p>
                          <div className="ent-citation-box">
                            <div className="citation-header">
                              <span className="citation-badge">Source Verification</span>
                              <span className="citation-page">Board Pack Page 42, Paragraph 3</span>
                            </div>
                            <blockquote className="citation-quote">
                              “Resolved: That the Board approves the FY27 Capital Reallocation Schedule as presented by the Chief Financial Officer and endorsed by the Risk Committee.”
                            </blockquote>
                          </div>
                        </div>

                        <div className="ent-actions-card">
                          <div className="ent-card-title">
                            <CheckCircle2 size={16} className="text-emerald" />
                            <span>Key Action Items & Deliverables</span>
                          </div>
                          <div className="ent-action-list">
                            <div className="ent-action-item">
                              <div className="action-meta">
                                <span className="action-priority priority-high">CRITICAL</span>
                                <span className="action-due">Due: Jul 01, 2026</span>
                              </div>
                              <p className="action-title">Finalize operational resilience charter prior to Q3 Audit Committee review.</p>
                              <span className="action-owner">Owner: Chief Risk Officer</span>
                            </div>
                            <div className="ent-action-item">
                              <div className="action-meta">
                                <span className="action-priority priority-med">STRATEGIC</span>
                                <span className="action-due">Due: Jul 15, 2026</span>
                              </div>
                              <p className="action-title">Deliver updated liquidity stress tests under revised ECB macro guidance.</p>
                              <span className="action-owner">Owner: Group Treasurer</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 2: TRENDS & ANOMALIES */}
                  {activeTab === 'trends' && (
                    <div className="ent-tab-view ent-tab-trends">
                      <div className="ent-view-header">
                        <div>
                          <span className="ent-tag-pill">LONGITUDINAL TELEMETRY</span>
                          <h3>Multi-Quarter Governance & Topic Drift Matrix</h3>
                          <p className="ent-meta-row">Comparative trajectory across 6 consecutive board sessions (Q1 2025 - Q2 2026)</p>
                        </div>
                        <div className="ent-anomaly-chip">
                          <AlertTriangle size={15} />
                          <span>1 Active Topic Anomaly Flagged</span>
                        </div>
                      </div>

                      <div className="ent-trends-grid">
                        <div className="ent-trend-chart-card">
                          <div className="chart-header">
                            <div>
                              <h4>Topic Discussion Density by Quarter</h4>
                              <p>Normalized mention frequency across formal minutes & audio logs</p>
                            </div>
                            <div className="chart-legend">
                              <span><i className="legend-box col-1" /> Capital & M&A</span>
                              <span><i className="legend-box col-2" /> Cyber & Risk</span>
                              <span><i className="legend-box col-3" /> ESG & Governance</span>
                            </div>
                          </div>

                          <div className="ent-bars-stage">
                            <div className="ent-bar-group">
                              <div className="bars-stack">
                                <span className="bar col-1" style={{ height: '55%' }} title="Capital: 55%" />
                                <span className="bar col-2" style={{ height: '35%' }} title="Risk: 35%" />
                                <span className="bar col-3" style={{ height: '20%' }} title="ESG: 20%" />
                              </div>
                              <span className="bar-label">Q1 25</span>
                            </div>
                            <div className="ent-bar-group">
                              <div className="bars-stack">
                                <span className="bar col-1" style={{ height: '62%' }} />
                                <span className="bar col-2" style={{ height: '40%' }} />
                                <span className="bar col-3" style={{ height: '24%' }} />
                              </div>
                              <span className="bar-label">Q2 25</span>
                            </div>
                            <div className="ent-bar-group">
                              <div className="bars-stack">
                                <span className="bar col-1" style={{ height: '48%' }} />
                                <span className="bar col-2" style={{ height: '58%' }} />
                                <span className="bar col-3" style={{ height: '30%' }} />
                              </div>
                              <span className="bar-label">Q3 25</span>
                            </div>
                            <div className="ent-bar-group">
                              <div className="bars-stack">
                                <span className="bar col-1" style={{ height: '42%' }} />
                                <span className="bar col-2" style={{ height: '72%' }} />
                                <span className="bar col-3" style={{ height: '35%' }} />
                              </div>
                              <span className="bar-label">Q4 25</span>
                            </div>
                            <div className="ent-bar-group">
                              <div className="bars-stack">
                                <span className="bar col-1" style={{ height: '50%' }} />
                                <span className="bar col-2" style={{ height: '85%' }} />
                                <span className="bar col-3" style={{ height: '42%' }} />
                              </div>
                              <span className="bar-label">Q1 26</span>
                            </div>
                            <div className="ent-bar-group highlighted">
                              <div className="bars-stack">
                                <span className="bar col-1" style={{ height: '65%' }} />
                                <span className="bar col-2" style={{ height: '94%' }} />
                                <span className="bar col-3" style={{ height: '48%' }} />
                              </div>
                              <span className="bar-label">Q2 26 (Current)</span>
                            </div>
                          </div>
                        </div>

                        <div className="ent-anomaly-alert-card">
                          <div className="alert-badge">
                            <AlertTriangle size={15} />
                            <span>STATISTICAL ANOMALY SURFACED</span>
                          </div>
                          <h4>Cybersecurity & Digital Resilience Shift</h4>
                          <p>
                            Discussion volume for <strong>Digital Operational Resilience (DORA compliance)</strong> surged <strong>+240%</strong> relative to the trailing 4-quarter baseline.
                          </p>
                          <div className="alert-meta-box">
                            <div className="meta-row">
                              <span>Confidence Metric:</span>
                              <strong>99.1% (Z-score +3.4)</strong>
                            </div>
                            <div className="meta-row">
                              <span>Originating Committee:</span>
                              <strong>Risk & Governance</strong>
                            </div>
                            <div className="meta-row">
                              <span>Recommended Action:</span>
                              <strong>Schedule Deep Dive in Q3</strong>
                            </div>
                          </div>
                          <Link to="/login" className="ent-btn-small ent-btn-block">
                            Analyze Historical Context <ArrowRight size={14} />
                          </Link>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 3: AUDIO & DIARIZATION */}
                  {activeTab === 'audio' && (
                    <div className="ent-tab-view ent-tab-audio">
                      <div className="ent-view-header">
                        <div>
                          <span className="ent-tag-pill">SPEAKER DIARIZATION PIPELINE</span>
                          <h3>Boardroom Audio Stream & Speaker Attribution</h3>
                          <p className="ent-meta-row">Session Recording #BRD-20260614 · Multi-microphone array audio input</p>
                        </div>
                        <div className="ent-audio-status">
                          <Mic size={14} className="text-emerald" />
                          <span>Acoustic Sync: 99.8% Precision</span>
                        </div>
                      </div>

                      {/* Simulated Audio Waveform Bar */}
                      <div className="ent-waveform-visualizer">
                        <div className="waveform-controls">
                          <span className="waveform-play">▶</span>
                          <span className="waveform-time">01:42:18 / 03:45:00</span>
                        </div>
                        <div className="waveform-bars">
                          {[30, 60, 45, 80, 95, 40, 65, 85, 50, 75, 90, 30, 45, 70, 85, 100, 65, 40, 80, 55, 90, 70, 40, 60, 85, 95, 50, 65, 30, 75, 85, 60, 45, 70, 90, 40].map((h, i) => (
                            <span key={i} style={{ height: `${h}%` }} className={i < 18 ? 'played' : ''} />
                          ))}
                        </div>
                        <span className="waveform-format">WAV · 24-bit / 48kHz</span>
                      </div>

                      {/* Diarized Feed */}
                      <div className="ent-diarized-stream">
                        <div className="diarized-entry">
                          <div className="speaker-badge chair">
                            <span>CHAIR</span>
                            <strong>Dame Eleanor Vance</strong>
                            <small>01:42:04</small>
                          </div>
                          <div className="speaker-text">
                            <p>“Thank you, Julian. The liquidity buffer appears solid, but I want to ensure the General Counsel is comfortable with the compliance covenants under the revised facility agreement.”</p>
                          </div>
                        </div>

                        <div className="diarized-entry">
                          <div className="speaker-badge counsel">
                            <span>LEGAL</span>
                            <strong>Marcus Chen (General Counsel)</strong>
                            <small>01:42:25</small>
                          </div>
                          <div className="speaker-text">
                            <p>“We have reviewed Section 8.4 in detail with external advisors. The negative pledge covenants have been amended as requested. Legal recommends proceeding with the resolution as formulated.”</p>
                            <span className="diarized-tag-action"><Check size={12} /> Auto-linked to Action Item #12 (Covenant Registry)</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 4: AUDIT & SECURITY */}
                  {activeTab === 'audit' && (
                    <div className="ent-tab-view ent-tab-audit">
                      <div className="ent-view-header">
                        <div>
                          <span className="ent-tag-pill">TAMPER-EVIDENT GOVERNANCE</span>
                          <h3>Cryptographic Audit Trail & Access Ledger</h3>
                          <p className="ent-meta-row">Immutable hash verification on every read, write, and export event</p>
                        </div>
                        <div className="ent-crypto-badge">
                          <LockKeyhole size={14} />
                          <span>SHA-256 Ledger Locked</span>
                        </div>
                      </div>

                      <div className="ent-audit-table-wrap">
                        <table className="ent-audit-table">
                          <thead>
                            <tr>
                              <th>Timestamp (UTC)</th>
                              <th>Actor</th>
                              <th>Role</th>
                              <th>Event Description</th>
                              <th>Resource Hash</th>
                              <th>Verification</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td>2026-06-14 11:24:08</td>
                              <td>sarah.jenkins@corp.com</td>
                              <td><span className="role-pill super-admin">Super Admin</span></td>
                              <td>Ingested Boardpack PDF & Audio Material</td>
                              <td><code>sha256:8f3c...b12a</code></td>
                              <td><span className="verif-pill valid"><CheckCircle2 size={12} /> VERIFIED</span></td>
                            </tr>
                            <tr>
                              <td>2026-06-14 11:26:40</td>
                              <td>sys.ai-engine@internal</td>
                              <td><span className="role-pill system">AI Engine</span></td>
                              <td>Extracted 6 Resolutions & 14 Action Items</td>
                              <td><code>sha256:4d1e...90f2</code></td>
                              <td><span className="verif-pill valid"><CheckCircle2 size={12} /> VERIFIED</span></td>
                            </tr>
                            <tr>
                              <td>2026-06-14 12:05:19</td>
                              <td>eleanor.vance@board.org</td>
                              <td><span className="role-pill editor">Chair / Editor</span></td>
                              <td>Reviewed Executive Digest & Signed Off</td>
                              <td><code>sha256:7a90...33c8</code></td>
                              <td><span className="verif-pill valid"><CheckCircle2 size={12} /> VERIFIED</span></td>
                            </tr>
                            <tr>
                              <td>2026-06-14 13:40:02</td>
                              <td>marcus.vance@audit.com</td>
                              <td><span className="role-pill viewer">Viewer</span></td>
                              <td>Generated Encrypted PPTX Board Deck</td>
                              <td><code>sha256:1b48...ee50</code></td>
                              <td><span className="verif-pill valid"><CheckCircle2 size={12} /> VERIFIED</span></td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>

                <div className="ent-window-footer">
                  <div className="footer-left">
                    <span className="ent-footer-status"><span className="status-live-dot" /> Connected to Enterprise Workspace Engine</span>
                  </div>
                  <div className="footer-right">
                    <Link to="/login" className="ent-footer-link">
                      Open in Full Screen Workspace <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Core Enterprise Capabilities (6 Pillars) */}
        <section className="ent-section ent-capabilities-section" id="capabilities">
          <div className="ent-container">
            <div className="ent-section-header text-center">
              <div className="ent-eyebrow">
                <Layers size={14} />
                <span>ENTERPRISE ARCHITECTURE</span>
              </div>
              <h2 className="ent-section-title">
                Engineered for the demands of the modern boardroom
              </h2>
              <p className="ent-section-subtitle">
                Six specialized pillars built to streamline governance, accelerate committee analysis, and protect confidential discussions.
              </p>
            </div>

            <div className="ent-caps-grid">
              {capabilities.map((cap, idx) => {
                const IconComponent = cap.icon;
                return (
                  <div className="ent-cap-card" key={idx}>
                    <div className="ent-cap-top">
                      <div className="ent-cap-icon-box">
                        <IconComponent size={22} />
                      </div>
                      <span className="ent-cap-badge">{cap.badge}</span>
                    </div>
                    <h3 className="ent-cap-title">{cap.title}</h3>
                    <p className="ent-cap-desc">{cap.description}</p>
                    <div className="ent-cap-footer">
                      <Link to="/login" className="ent-cap-link">
                        {cap.linkText} <ArrowRight size={14} />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* 3-Step Enterprise Governance Workflow */}
        <section className="ent-section ent-workflow-section" id="workflow">
          <div className="ent-container">
            <div className="ent-section-header text-center">
              <div className="ent-eyebrow">
                <Upload size={14} />
                <span>END-TO-END METHODOLOGY</span>
              </div>
              <h2 className="ent-section-title">
                From chaotic meeting files to decisive governance
              </h2>
              <p className="ent-section-subtitle">
                A seamless, automated pipeline designed to elevate corporate secretariats and board members.
              </p>
            </div>

            <div className="ent-workflow-steps">
              <div className="ent-wf-step">
                <div className="ent-wf-number">01</div>
                <div className="ent-wf-content">
                  <div className="ent-wf-icon"><Upload size={20} /></div>
                  <h4>Secure Ingestion & Multi-Speaker Diarization</h4>
                  <p>
                    Upload board packs, confidential committee attachments (PDF/DOCX), or audio recordings. The system automatically OCRs, transcribes, and normalizes all source documents into an encrypted index.
                  </p>
                  <ul className="ent-wf-list">
                    <li><Check size={14} /> Multi-language transcription support</li>
                    <li><Check size={14} /> Speaker diarization & timestamping</li>
                  </ul>
                </div>
              </div>

              <div className="ent-wf-step">
                <div className="ent-wf-number">02</div>
                <div className="ent-wf-content">
                  <div className="ent-wf-icon"><Cpu size={20} /></div>
                  <h4>LLM Synthesis & Citation Verification</h4>
                  <p>
                    Proprietary reasoning models extract formal resolutions, strategic themes, and action commitments. Every extracted fact contains interactive citations directly mapped back to source text.
                  </p>
                  <ul className="ent-wf-list">
                    <li><Check size={14} /> Named entity recognition (NER)</li>
                    <li><Check size={14} /> Longitudinal multi-quarter trend radar</li>
                  </ul>
                </div>
              </div>

              <div className="ent-wf-step">
                <div className="ent-wf-number">03</div>
                <div className="ent-wf-content">
                  <div className="ent-wf-icon"><FileSpreadsheet size={20} /></div>
                  <h4>Committee Reporting & PPTX Presentation</h4>
                  <p>
                    Export polished executive summaries into PowerPoint decks or PDFs. Schedule automated report dispatch to directors and committee chairs ahead of upcoming statutory deadlines.
                  </p>
                  <ul className="ent-wf-list">
                    <li><Check size={14} /> 1-click PowerPoint presentation export</li>
                    <li><Check size={14} /> Automated schedule delivery system</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Enterprise Security & Governance Spotlight */}
        <section className="ent-section ent-security-section" id="security">
          <div className="ent-container">
            <div className="ent-security-box">
              <div className="ent-security-left">
                <div className="ent-eyebrow text-emerald">
                  <LockKeyhole size={14} />
                  <span>GOVERNANCE & TRUST GUARANTEES</span>
                </div>
                <h2>Security architectures built for boardroom confidentiality</h2>
                <p>
                  Board records contain the organization's most sensitive discussions—from M&A deliberations to regulatory risk disclosures. We provide defense-in-depth protection at every tier.
                </p>

                <div className="ent-sec-features">
                  <div className="sec-feature">
                    <ShieldCheck size={20} className="text-emerald" />
                    <div>
                      <strong>AES-256 & TLS 1.3 Encryption</strong>
                      <p>Data is cryptographically protected both at rest and in transit across all endpoints.</p>
                    </div>
                  </div>
                  <div className="sec-feature">
                    <Users size={20} className="text-emerald" />
                    <div>
                      <strong>Granular Role-Based Access Control (RBAC)</strong>
                      <p>Restrict visibility across Super Admin, Admin, Editor, and Viewer privileges.</p>
                    </div>
                  </div>
                  <div className="sec-feature">
                    <Database size={20} className="text-emerald" />
                    <div>
                      <strong>Zero Data Retention Processing</strong>
                      <p>Customer data is never used to train generalized foundation models.</p>
                    </div>
                  </div>
                </div>

                <div className="ent-security-cta">
                  <Link to="/login" className="ent-btn-primary">
                    Review Security Specs <ArrowRight size={15} />
                  </Link>
                </div>
              </div>

              <div className="ent-security-right">
                <div className="ent-sec-badge-card">
                  <div className="sec-card-header">
                    <Terminal size={16} />
                    <span>Compliance Verification</span>
                  </div>
                  <div className="sec-compliance-list">
                    <div className="sec-comp-row">
                      <span className="sec-comp-name">SOC2 Type II Controls</span>
                      <span className="sec-comp-status">ALIGNED</span>
                    </div>
                    <div className="sec-comp-row">
                      <span className="sec-comp-name">ISO/IEC 27001 Security</span>
                      <span className="sec-comp-status">COMPLIANT</span>
                    </div>
                    <div className="sec-comp-row">
                      <span className="sec-comp-name">GDPR & Confidentiality</span>
                      <span className="sec-comp-status">ENFORCED</span>
                    </div>
                    <div className="sec-comp-row">
                      <span className="sec-comp-name">Immutable Audit Trail</span>
                      <span className="sec-comp-status">ACTIVE</span>
                    </div>
                    <div className="sec-comp-row">
                      <span className="sec-comp-name">Dedicated Private Cloud / On-Prem</span>
                      <span className="sec-comp-status">AVAILABLE</span>
                    </div>
                  </div>
                  <div className="sec-card-footer">
                    <small>All governance transactions cryptographically anchored to tenant ledger.</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Executive Voices / Social Proof */}
        <section className="ent-section ent-testimonials-section">
          <div className="ent-container">
            <div className="ent-section-header text-center">
              <div className="ent-eyebrow">
                <Users size={14} />
                <span>EXECUTIVE VALIDATION</span>
              </div>
              <h2 className="ent-section-title">
                Trusted by board leaders & corporate secretaries
              </h2>
            </div>

            <div className="ent-quotes-grid">
              <div className="ent-quote-card">
                <p className="quote-body">
                  “The ability to search across five years of committee minutes and have the exact context, speaker quote, and approved resolution displayed in seconds has transformed our audit preparation.”
                </p>
                <div className="quote-author">
                  <div className="author-avatar">SC</div>
                  <div>
                    <strong>Sophia Caldwell</strong>
                    <span>General Counsel & Company Secretary, FTSE 100 Financial</span>
                  </div>
                </div>
              </div>

              <div className="ent-quote-card">
                <p className="quote-body">
                  “Board Minutes gave our directors a single source of truth. The automated PowerPoint export saves our secretariat team over forty hours of preparation for each quarterly board cycle.”
                </p>
                <div className="quote-author">
                  <div className="author-avatar">RH</div>
                  <div>
                    <strong>Robert Henderson</strong>
                    <span>Chair of the Audit & Risk Committee, Global Infrastructure</span>
                  </div>
                </div>
              </div>

              <div className="ent-quote-card">
                <p className="quote-body">
                  “The longitudinal anomaly radar flagged a subtle compliance trend in our European entities two quarters before our internal auditors noticed it. An indispensable governance tool.”
                </p>
                <div className="quote-author">
                  <div className="author-avatar">AL</div>
                  <div>
                    <strong>Dr. Amira Larsson</strong>
                    <span>Non-Executive Director, Healthcare & Diagnostics</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Interactive FAQ Accordion */}
        <section className="ent-section ent-faq-section" id="faq">
          <div className="ent-container">
            <div className="ent-section-header text-center">
              <div className="ent-eyebrow">
                <Search size={14} />
                <span>ENTERPRISE PROCUREMENT FAQ</span>
              </div>
              <h2 className="ent-section-title">Frequently Asked Questions</h2>
              <p className="ent-section-subtitle">
                Everything your legal, IT, and governance teams need to know about deployment and compliance.
              </p>
            </div>

            <div className="ent-faq-list">
              {faqs.map((faq, i) => (
                <div
                  className={`ent-faq-item ${openFaq === i ? 'open' : ''}`}
                  key={i}
                  onClick={() => setOpenFaq(openFaq === i ? -1 : i)}
                >
                  <button type="button" className="ent-faq-question" aria-expanded={openFaq === i}>
                    <span>{faq.q}</span>
                    {openFaq === i ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </button>
                  {openFaq === i && (
                    <div className="ent-faq-answer">
                      <p>{faq.a}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Final Conversion CTA */}
        <section className="ent-cta-section">
          <div className="ent-container">
            <div className="ent-cta-card">
              <div className="ent-cta-content">
                <div className="ent-pill-tag">
                  <Sparkles size={14} />
                  <span>Enterprise Deployment Ready</span>
                </div>
                <h2>Elevate your board governance today</h2>
                <p>
                  Join corporate secretaries, legal counsels, and directors who turn unstructured meeting records into clear, auditable governance decisions.
                </p>
                <div className="ent-cta-buttons">
                  <Link to="/login" className="ent-btn-primary ent-btn-hero">
                    Enter Board Workspace <ArrowRight size={18} />
                  </Link>
                  <Link to="/login" className="ent-btn-ghost ent-btn-hero">
                    Request Governance Briefing
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Enterprise Multi-Column Footer */}
      <footer className="ent-footer">
        <div className="ent-container">
          <div className="ent-footer-grid">
            <div className="ent-footer-brand-col">
              <div className="ent-brand">
                <img src="/ITDS_LOGO.png" alt="ITDS" className="ent-brand-logo" />
                <div className="ent-brand-text">
                  <span className="ent-brand-title">BOARD MINUTES</span>
                  <span className="ent-brand-badge">ENTERPRISE</span>
                </div>
              </div>
              <p className="ent-footer-desc">
                High-assurance AI intelligence platform for board records, committee resolutions, and longitudinal governance analytics.
              </p>
              <div className="ent-footer-cert">
                <ShieldCheck size={15} />
                <span>SOC2 Type II Aligned · 256-bit AES</span>
              </div>
            </div>

            <div className="ent-footer-links-col">
              <h5>Platform</h5>
              <a href="#console">Interactive Console</a>
              <a href="#capabilities">Multi-Modal Ingestion</a>
              <a href="#capabilities">Voice Diarization</a>
              <a href="#capabilities">Longitudinal Trends</a>
              <a href="#capabilities">Presentation Export</a>
            </div>

            <div className="ent-footer-links-col">
              <h5>Governance & Trust</h5>
              <a href="#security">Role-Based Access (RBAC)</a>
              <a href="#security">Cryptographic Audit Ledger</a>
              <a href="#security">Data Isolation Architecture</a>
              <a href="#security">Zero Data Retention Policy</a>
              <a href="#faq">Procurement FAQ</a>
            </div>

            <div className="ent-footer-links-col">
              <h5>Access</h5>
              <Link to="/login">Sign In to Workspace</Link>
              <Link to="/login">Super Admin Console</Link>
              <Link to="/login">Report Dispatch Hub</Link>
              <Link to="/login">User Provisioning</Link>
            </div>
          </div>

          <div className="ent-footer-bottom">
            <div className="ent-footer-bottom-left">
              <span>© 2026 ITDS Frameworks. All rights reserved.</span>
              <span className="sep">•</span>
              <span>Enterprise Board Governance System</span>
            </div>
            <div className="ent-footer-bottom-right">
              <span className="status-indicator">
                <span className="status-live-dot" /> All Systems Operational (99.98%)
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
