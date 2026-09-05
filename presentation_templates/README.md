Sample PPTX template generator

Files:
- generate_pptx_template.py — simple script using `python-pptx` to create a template

Slides included in the template:
1. Title slide — title + subtitle
2. Agenda — bullet list of sections
3. Executive Summary — top takeaways and placeholders
4. Top Themes — chart placeholder (replace with PNG chart image)
5. Anomalies & Recommendations — bullet list of detected anomalies and suggested actions
6. Notes & Next Steps — closing slide

Usage:
1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Run the generator:

```powershell
python presentation_templates\generate_pptx_template.py
```

Output:
- `uploads/presentations/sample_presentation_template.pptx` — open in PowerPoint or LibreOffice Impress

Next steps (optional):
- Render Chart.js charts to PNG and paste into the chart placeholder slide.
- Replace placeholder text with actual values from the analytics APIs.
- Integrate into a background job for automated generation and storage.
