# PPTX Export Feature — Implementation Complete

## Features Added

### Backend

**New API endpoints** in `/api/reports`:
- `GET /api/reports/presentation/templates` → List available template themes (corporate, ocean, sunrise)
- `POST /api/reports/presentation` → Generate and download themed PPTX file with live data

**Payload builder** (`_build_summary_payload`) consolidates:
- Top themes + sentiment analysis + anomalies + recommendations  
- Reused across executive summary, HTML export, and PPTX routes

**Themed PPTX generator** (`_build_presentation_bytes`) builds 6-slide decks:
1. **Title slide** — title, author, generation timestamp
2. **Executive summary** — key findings + statistics (Meetings/Themes/Sentiment/Anomalies)
3. **Top themes** — bar chart of top-N themes with mention counts
4. **Sentiment breakdown** — doughnut chart (positive/neutral/negative with trend)
5. **Anomalies + recommendations** — detailed findings with suggested actions
6. **Next steps** — closing slide with 3-point action plan

**Three color themes**:
- **Corporate Blue** (dark blue/gray accents)
- **Ocean Teal** (teal/turquoise)
- **Sunrise Amber** (orange/warm tones)

Each theme includes custom RGB palettes for text, accent, sentiment colors, and backgrounds.

### Frontend

**Export controls added in 3 places**:

1. **ReportsPage** (`/reports`):
   - "Export Presentation (PPTX)" button
   - Modal with options:
     - Template theme selector (dropdown)
     - Top themes count (3–10 range)
     - Include anomalies toggle
     - Include speaker notes toggle
   - Download triggers `/api/reports/presentation`

2. **ExecutiveSummaryCard** (nested in Reports):
   - Theme selector dropdown + "Download PPTX" button
   - Defaults: 6 themes, anomalies on, speaker notes on

3. **TrendAnalysisDashboard** (`/trend-analysis`):
   - "Create Slides" link button in header
   - Links to `/reports?year={selectedYear}` to pre-select year

4. **Dashboard** (`/dashboard`):
   - "Create Slides" button in header
   - Links to `/reports`

**API integration**:
- Added `reportsAPI.getPresentationTemplates()` and `reportsAPI.exportPresentation(payload)` helpers
- Handles blob download with sanitized filename: `governance-presentation-YYYY-{theme}.pptx`

**Styling**:
- Modal overlay with card-based design
- Teal-accented buttons ("Create Slides", "Export PPTX") for visual differentiation
- Dark theme support across all controls
- Responsive layout (mobile-friendly modal actions)

---

## Usage Flows

### Quick Export (1-click)
1. Go to Dashboard, Trends, or Reports
2. Click "Create Slides" or "Export Presentation (PPTX)"
3. (Optional) Select template theme and options
4. Click "Download PPTX"
5. PPTX auto-downloads with live data snapshot

### Scheduled/Shared
- Export once, share file with stakeholders
- Each export includes generation timestamp and data sources for audit trail
- Speaker notes provide guidance per slide

---

## Technical Details

- **Dependencies**: `python-pptx`, `Pillow` (already in requirements.txt)
- **File size**: ~57 KB per PPTX (all themes)
- **Generation time**: < 1 second (sync endpoint)
- **Payload reuse**: Shares `_build_summary_payload()` with HTML and API routes
- **Color mapping**: Hex strings → RGB tuples via `_hex_to_rgb()`
- **Chart data**: Uses `CategoryChartData` to embed native PPTX bar/doughnut charts

---

## Next Steps (Optional)

1. **Background jobs**: Move to async (Celery/RQ) if PPTX generation > 3s
2. **PDF export**: Add server-side PPTX→PDF conversion (LibreOffice headless or cloud API)
3. **Custom branding**: Allow orgs to upload logos, pick custom fonts
4. **More templates**: E.g., minimalist, presentation-heavy, data-dense layouts
5. **Scheduled delivery**: Email PPTX to stakeholders on cadence (integrate with email_service.py)

---

## Files Changed

**Backend**:
- [itds_env/app/report_generator.py](itds_env/app/report_generator.py) — +450 LOC (generators, themes, API endpoints)
- [requirements.txt](requirements.txt) — added `python-pptx`

**Frontend**:
- [itds_env/frontend/src/api/api.js](itds_env/frontend/src/api/api.js) — added `reportsAPI` methods
- [itds_env/frontend/src/components/ReportsPage.js](itds_env/frontend/src/components/ReportsPage.js) — modal + export logic
- [itds_env/frontend/src/components/ReportsPage.css](itds_env/frontend/src/components/ReportsPage.css) — modal styles
- [itds_env/frontend/src/components/ExecutiveSummaryCard.js](itds_env/frontend/src/components/ExecutiveSummaryCard.js) — PPTX controls
- [itds_env/frontend/src/components/ExecutiveSummaryCard.css](itds_env/frontend/src/components/ExecutiveSummaryCard.css) — PPTX styles
- [itds_env/frontend/src/components/TrendAnalysisDashboard.js](itds_env/frontend/src/components/TrendAnalysisDashboard.js) — "Create Slides" link
- [itds_env/frontend/src/components/TrendAnalysisDashboard.css](itds_env/frontend/src/components/TrendAnalysisDashboard.css) — link styling
- [itds_env/frontend/src/components/Dashboard.js](itds_env/frontend/src/components/Dashboard.js) — "Create Slides" button

**Tests**:
- [test_presentation_export.py](test_presentation_export.py) — unit tests (payload builder + all 3 themes)

---

## Validation ✓

- Backend smoke test: Successfully generated 57 KB PPTX files for all 3 themes
- Payload builder: Returns all required fields (themes, sentiment, anomalies, recommendations)
- Frontend code: No syntax/lint errors
- API wiring: Endpoints registered in Flask blueprint
- Modal/UI: Responsive, accessible (ARIA labels, keyboard support)

---

**Status**: Ready for testing. Restart backend (`python run.py`) and frontend (`npm start`), then:
1. Navigate to `/reports`
2. Click "Export Presentation (PPTX)"
3. Select theme (e.g., "Ocean Teal")
4. Click "Download PPTX"
5. Open downloaded file in PowerPoint/LibreOffice to preview 6 slides with live data charts
