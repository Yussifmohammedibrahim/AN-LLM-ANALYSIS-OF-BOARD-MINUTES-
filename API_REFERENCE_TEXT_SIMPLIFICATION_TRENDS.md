# API Reference: Text Simplification & Trend Analysis

## Text Simplification Endpoints

### Simplify Individual Text
```
POST /api/ai/simplify
Authorization: Bearer <token>
Content-Type: application/json

{
  "text": "The committee convened to deliberate on curriculum augmentation strategies...",
  "max_length": 150
}

Response:
{
  "original_text": "...",
  "simplified_text": "...",
  "simplified": true,
  "length_reduction": 245,
  "model": "t5"
}
```

### Simplify All Meeting Segments
```
POST /api/ai/simplify/meeting/<meeting_id>
Authorization: Bearer <token>

Response:
{
  "meeting_id": 123,
  "simplified_count": 15,
  "segments": [
    {
      "segment_id": 1,
      "original_text": "...",
      "simplified_text": "..."
    }
  ]
}
```

---

## Trend Analysis Endpoints

### Get Monthly Trends
```
GET /api/ai/theme-trends?year=2026
Authorization: Bearer <token>

Response:
{
  "year": 2026,
  "period": "2026-01 to 2026-12",
  "trends": [
    {
      "month": "2026-01",
      "meeting_count": 3,
      "growth_rate": 0,
      "trend": "stable"
    },
    {
      "month": "2026-02",
      "meeting_count": 5,
      "growth_rate": 66.7,
      "trend": "up"
    }
  ],
  "statistics": {
    "total_meetings": 42,
    "average_per_month": 3.5,
    "peak_month": "2026-08",
    "peak_count": 8
  },
  "insight": "Meetings are increasing. Latest month (2026-02) had 5 meetings (+66.7% vs previous)."
}
```

### Get Theme Frequency Analysis
```
GET /api/ai/theme-frequency?year=2026
Authorization: Bearer <token>

Response:
[
  {
    "name": "Budget Discussion",
    "keywords": ["budget", "funding", "financial", "cost", "expense"],
    "total_mentions": 35,
    "monthly_distribution": {
      "2026-01": 2,
      "2026-02": 5,
      "2026-03": 4
    },
    "growth_trend": "increasing",
    "growth_rate": 18.5
  }
]
```

### Get Emerging Themes
```
GET /api/ai/emerging-themes?year=2026
Authorization: Bearer <token>

Response:
[
  {
    "name": "Infrastructure Issues",
    "keywords": ["facility", "maintenance", "building"],
    "total_mentions": 12,
    "meeting_count": 8,
    "frequency": 19.0,
    "growth_rate": 45.8
  }
]
```

### Get Recurring Issues
```
GET /api/ai/recurring-issues?year=2026
Authorization: Bearer <token>

Response:
[
  {
    "name": "Curriculum Updates",
    "keywords": ["curriculum", "course", "program", "academic"],
    "meeting_count": 31,
    "total_meetings": 42,
    "frequency": 73.8
  }
]
```

### Get Sentiment Trends
```
GET /api/ai/sentiment-trends?year=2026
Authorization: Bearer <token>

Response:
[
  {
    "month": "2026-01",
    "positive": 45,
    "negative": 12,
    "neutral": 30,
    "total": 87,
    "positive_rate": 51.7
  },
  {
    "month": "2026-02",
    "positive": 52,
    "negative": 8,
    "neutral": 35,
    "total": 95,
    "positive_rate": 54.7
  }
]
```

---

## cURL Examples

### Test Text Simplification
```bash
curl -X POST http://localhost:5001/api/ai/simplify \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The interdisciplinary committee convened to deliberate upon the paradigm shift in pedagogical methodologies",
    "max_length": 120
  }'
```

### Test Trend Analysis
```bash
curl -X GET "http://localhost:5001/api/ai/theme-trends?year=2026" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5001/api/ai/theme-frequency?year=2026" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5001/api/ai/emerging-themes?year=2026" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5001/api/ai/recurring-issues?year=2026" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl -X GET "http://localhost:5001/api/ai/sentiment-trends?year=2026" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Python Client Examples

### Text Simplification
```python
import requests

token = "YOUR_JWT_TOKEN"
headers = {"Authorization": f"Bearer {token}"}

# Single text
response = requests.post(
    "http://localhost:5001/api/ai/simplify",
    json={
        "text": "The comprehensive strategic review paradigm...",
        "max_length": 150
    },
    headers=headers
)
print(response.json())

# Meeting segments
response = requests.post(
    "http://localhost:5001/api/ai/simplify/meeting/123",
    headers=headers
)
print(response.json())
```

### Trend Analysis
```python
import requests
from datetime import datetime

token = "YOUR_JWT_TOKEN"
headers = {"Authorization": f"Bearer {token}"}
year = datetime.now().year

# Theme trends
response = requests.get(
    f"http://localhost:5001/api/ai/theme-trends?year={year}",
    headers=headers
)
trends_data = response.json()
print(f"Total meetings: {trends_data['statistics']['total_meetings']}")
print(f"Key insight: {trends_data['insight']}")

# Emerging themes
response = requests.get(
    f"http://localhost:5001/api/ai/emerging-themes?year={year}",
    headers=headers
)
emerging = response.json()
for theme in emerging[:3]:
    print(f"📈 {theme['name']}: +{theme['growth_rate']}% growth")

# Recurring issues
response = requests.get(
    f"http://localhost:5001/api/ai/recurring-issues?year={year}",
    headers=headers
)
recurring = response.json()
for issue in recurring[:3]:
    print(f"🔁 {issue['name']}: appears in {issue['frequency']:.0f}% of meetings")
```

---

## Error Handling

All endpoints return standard error responses:

```json
{
  "error": "Error message describing what went wrong",
  "details": "Optional additional context"
}
```

Common HTTP Status Codes:
- `200 OK` - Request successful
- `400 Bad Request` - Missing required parameters
- `401 Unauthorized` - Invalid or missing JWT token
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error (check logs)

---

## Rate Limiting Notes

- Text Simplification: 
  - First call: ~2-5s (model loading)
  - Subsequent: ~1s per request
  - Batch: ~2-3s for 10 items

- Trend Analysis:
  - ~500ms-2s depending on data volume
  - Results cached per year

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <jwt_token>
```

Obtain token via login endpoint and include in all requests.

---

## Data Format Notes

### max_length (Text Simplification)
- Range: 50-512 characters
- Default: 150
- Output will be shorter than input (goal is simplification)

### year (Trend Analysis)
- Optional, defaults to current year
- Format: YYYY (e.g., 2026)
- Supported: 2024, 2025, 2026, 2027

---

## Troubleshooting

### Models Not Loading
```
Error: "Simplification model unavailable"
```
Solution: Ensure T5 model is downloaded (~500MB). First request will cache it.

### No Trend Data
```
Response: []
```
Solution: Ensure meetings exist and theme extraction has been run.

### Slow Responses
```
Simplification taking >5 seconds
```
Solution: First request loads model. Subsequent requests are faster. Consider batch processing.

---

## Performance Tips

1. **Batch Text**: Use `/simplify` in a loop rather than `/simplify/meeting/<id>` for single texts
2. **Cache Results**: Results are automatically saved to database
3. **Filter by Year**: Use year parameter to limit trend data size
4. **Limit Themes**: Trend analysis limits to top N by default

---

## Integration Guide

See `IMPLEMENTATION_GUIDE_TEXT_SIMPLIFICATION_TRENDS.md` for step-by-step integration instructions.
