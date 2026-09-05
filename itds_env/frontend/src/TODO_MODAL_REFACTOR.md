# ProfileUploadModal Refactor Plan

**Objective:** Fixed-size centered popup, no expansion on file select

**Current Issues:**
- Stretches full width
- Grows after image select
- Large unstructured UI

**Fix Plan:**
1. [ ] Force fixed modal size: max-width: 400px, overflow: hidden
2. [ ] Fixed image preview: 80x80px
3. [ ] Compact upload box: padding 16px, fixed height
4. [ ] Add CSS fallbacks to App.css
5. [ ] Remove dynamic sizing

**Expected Result:** Compact dialog matching login modal

