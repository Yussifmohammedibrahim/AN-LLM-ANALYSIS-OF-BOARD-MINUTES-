import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  Check,
  FileAudio,
  FileText,
  LockKeyhole,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
} from 'lucide-react';
import './LandingPage.css';

const capabilities = [
  {
    icon: FileText,
    number: '01',
    title: 'Bring minutes together',
    description: 'Upload board documents and recordings into one searchable workspace, ready for review and analysis.',
  },
  {
    icon: Sparkles,
    number: '02',
    title: 'Turn content into signal',
    description: 'Surface summaries, topics, sentiment, entities, and trends without losing the original context.',
  },
  {
    icon: BarChart3,
    number: '03',
    title: 'Move from insight to action',
    description: 'Share reports, follow themes over time, and give leadership a clearer view of what needs attention.',
  },
];

const LandingPage = () => (
  <div className="landing-page">
    <header className="landing-nav">
      <a className="landing-brand" href="#top" aria-label="ITDS home">
        <img src="/ITDS_LOGO.png" alt="" />
        <span>ITDS</span>
      </a>
      <nav className="landing-nav-links" aria-label="Main navigation">
        <a href="#capabilities">Capabilities</a>
        <a href="#workflow">Workflow</a>
        <a href="#security">Security</a>
      </nav>
      <Link className="landing-nav-action" to="/login">
        Sign in <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </header>

    <main id="top">
      <section className="landing-hero">
        <div className="landing-hero-copy">
          <p className="landing-eyebrow"><span /> Board intelligence, made usable</p>
          <h1>Make every board meeting easier to understand.</h1>
          <p className="landing-hero-lede">
            ITDS helps teams turn meeting minutes and recordings into structured insight, so decisions do not disappear into documents.
          </p>
          <div className="landing-hero-actions">
            <Link className="landing-primary-button" to="/login">
              Enter workspace <ArrowRight size={18} aria-hidden="true" />
            </Link>
            <a className="landing-text-link" href="#workflow">
              See how it works <span aria-hidden="true">↓</span>
            </a>
          </div>
          <div className="landing-trust-line">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>Built for governed review and repeatable reporting</span>
          </div>
        </div>

        <div className="landing-hero-visual" aria-label="Preview of the ITDS analysis workspace">
          <div className="landing-visual-topline">
            <span className="landing-window-dots"><i /><i /><i /></span>
            <span>Meeting intelligence / Q2 review</span>
            <span className="landing-live-status"><b /> Ready</span>
          </div>
          <div className="landing-visual-body">
            <div className="landing-visual-sidebar">
              <span className="landing-mini-logo">I</span>
              <span className="landing-sidebar-line active" />
              <span className="landing-sidebar-line" />
              <span className="landing-sidebar-line" />
              <span className="landing-sidebar-line short" />
            </div>
            <div className="landing-dashboard-preview">
              <div className="landing-preview-heading">
                <div><small>BOARD REVIEW</small><strong>Executive summary</strong></div>
                <span className="landing-preview-date">14 JUN 2026</span>
              </div>
              <div className="landing-metric-row">
                <div><small>Documents analysed</small><strong>28</strong><span>+12% this quarter</span></div>
                <div><small>Key themes</small><strong>06</strong><span>Across 4 meetings</span></div>
                <div><small>Open actions</small><strong>19</strong><span className="warning">Needs review</span></div>
              </div>
              <div className="landing-preview-grid">
                <div className="landing-theme-panel">
                  <div className="landing-panel-title"><span>Theme movement</span><BarChart3 size={15} /></div>
                  <div className="landing-bars"><span style={{ height: '42%' }} /><span style={{ height: '63%' }} /><span style={{ height: '52%' }} /><span style={{ height: '78%' }} /><span style={{ height: '68%' }} /><span style={{ height: '92%' }} /><span style={{ height: '82%' }} /></div>
                  <div className="landing-chart-labels"><span>JAN</span><span>FEB</span><span>MAR</span><span>APR</span><span>MAY</span><span>JUN</span></div>
                </div>
                <div className="landing-insight-panel">
                  <div className="landing-panel-title"><span>Priority insight</span><Sparkles size={15} /></div>
                  <p>Operational resilience is now the dominant theme across recent meetings.</p>
                  <div className="landing-insight-tag">3 mentions rising</div>
                </div>
              </div>
              <div className="landing-preview-footer"><span><Check size={14} /> Analysis complete</span><span>View report <ArrowRight size={14} /></span></div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-proof-strip" aria-label="Platform capabilities">
        <span>ONE WORKSPACE</span><i /><span>DOCUMENTS TO DECISIONS</span><i /><span>BUILT FOR THE BOARDROOM</span>
      </section>

      <section className="landing-section landing-capabilities" id="capabilities">
        <div className="landing-section-heading">
          <p className="landing-eyebrow"><span /> One connected system</p>
          <h2>Less time sorting information.<br /><em>More time acting on it.</em></h2>
          <p>Designed for the full rhythm of governance work, from the first upload to the final report.</p>
        </div>
        <div className="landing-capability-grid">
          {capabilities.map(({ icon: Icon, number, title, description }) => (
            <article className="landing-capability" key={number}>
              <div className="landing-capability-top"><span>{number}</span><Icon size={21} aria-hidden="true" /></div>
              <h3>{title}</h3>
              <p>{description}</p>
              <span className="landing-capability-rule" />
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-workflow" id="workflow">
        <div className="landing-workflow-mark"><Upload size={25} /><span>ITDS<br />WORKFLOW</span></div>
        <div className="landing-workflow-copy">
          <p className="landing-eyebrow"><span /> From source to signal</p>
          <h2>A workflow your team can trust.</h2>
          <p>Keep the source material, analysis, and decisions connected. Every insight can be traced back to the meeting context that created it.</p>
          <div className="landing-workflow-list">
            <div><span>1</span><p><strong>Upload</strong> PDF, DOCX, or audio meeting material.</p></div>
            <div><span>2</span><p><strong>Analyse</strong> content with summaries, themes, and intelligent search.</p></div>
            <div><span>3</span><p><strong>Report</strong> findings in a format that leadership can use.</p></div>
          </div>
        </div>
        <div className="landing-workflow-quote">
          <Search size={20} aria-hidden="true" />
          <p>“Find the thread across meetings, not just the sentence in front of you.”</p>
          <span>— The ITDS approach</span>
        </div>
      </section>

      <section className="landing-section landing-security" id="security">
        <div>
          <p className="landing-eyebrow"><span /> Responsible by design</p>
          <h2>Governance work deserves a governed system.</h2>
        </div>
        <div className="landing-security-items">
          <div><LockKeyhole size={19} /><p><strong>Controlled access</strong><span>Role-aware workspaces and secure sign-in.</span></p></div>
          <div><FileAudio size={19} /><p><strong>Flexible inputs</strong><span>Documents and recordings in one workflow.</span></p></div>
          <div><ShieldCheck size={19} /><p><strong>Traceable insight</strong><span>Keep analysis connected to source material.</span></p></div>
        </div>
      </section>

      <section className="landing-cta">
        <div><p className="landing-eyebrow"><span /> Ready when your next meeting is</p><h2>Give your board materials<br /><em>a longer life.</em></h2></div>
        <Link className="landing-primary-button" to="/login">Open ITDS workspace <ArrowRight size={18} aria-hidden="true" /></Link>
      </section>
    </main>

    <footer className="landing-footer"><span>© 2026 ITDS</span><span>Board intelligence for clearer decisions</span><span>Secure workspace access</span></footer>
  </div>
);

export default LandingPage;
