# AN-LLM Analysis of Board Minutes

An AI-assisted platform for uploading and analysing board meeting minutes. The application combines a Flask backend with a React frontend and supports document processing, summarisation, question answering, topic and sentiment analysis, trend analysis, reporting, and presentation export.

## Features

- Upload and process PDF, DOCX, and audio meeting files
- Extract, summarise, and simplify meeting content
- Analyse topics, themes, sentiment, named entities, and trends
- Ask questions about processed meeting material
- Manage users, authentication, notifications, and scheduled reports
- Export analysis and presentations

## Technology

- **Backend:** Python, Flask, SQLite
- **Frontend:** React, Create React App, CRACO
- **AI/ML:** Transformers, Sentence Transformers, BERTopic, scikit-learn, OpenAI-compatible APIs
- **Processing:** PyMuPDF, PyPDF2, python-docx, Tesseract OCR, FFmpeg
- **Optional services:** Redis/RQ for background jobs and web push notifications

## Requirements

- Python 3.10 or newer
- Node.js and npm
- Tesseract OCR and FFmpeg for OCR and audio processing
- Redis if background queue processing is required

## Local Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item itds_env\.env.example itds_env\.env
```

Edit `itds_env/.env` and replace the placeholder values with local credentials and secure application secrets. Never commit that file. AI provider keys are optional for features that have local fallbacks, but are required for the corresponding hosted AI integrations.

Install and start the frontend:

```powershell
npm run install:all
npm run dev
```

In a second terminal, start the backend:

```powershell
.\.venv\Scripts\Activate.ps1
npm run start:backend
```

The frontend runs on the port selected by the React development server. The backend development command uses port `5000`; the production container uses port `5001`.

## Docker

The Docker image installs the backend dependencies, Tesseract, and FFmpeg. To start the configured services:

```powershell
docker compose up --build
```

Keep production secrets in environment variables or an untracked `.env` file. Persist the application database and uploaded files outside the container.

## Project Layout

```text
itds_env/app/             Flask application, AI services, models, and routes
itds_env/frontend/        React application
scripts/                  Database, maintenance, and evaluation scripts
tests/                    Test assets and test code
presentation_templates/   Presentation generation helpers
docs/                     Development notes and backlog
```

Generated databases, uploaded documents, logs, virtual environments, dependency folders, build output, and local environment files are excluded by `.gitignore`.

## Useful Commands

```powershell
npm run build           # Build the frontend
npm run dev             # Start the frontend development server
npm run start:backend  # Start the Flask backend
```

## Security

Do not commit API keys, SMTP passwords, JWT/application secrets, private keys, databases containing user data, or uploaded documents. Use `itds_env/.env.example` as the configuration template and rotate any credential that may have been exposed.