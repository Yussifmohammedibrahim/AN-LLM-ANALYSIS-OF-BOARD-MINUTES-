# Chapter 3 Mermaid Diagrams

Use these Mermaid diagrams directly in your thesis draft or convert them into images for figure insertion.

## Figure 3.1 - DSR Process Model

```mermaid
flowchart LR
    A[1. Problem Identification\n& Motivation] --> B[2. Define Objectives\nfor a Solution]
    B --> C[3. Design & Development]
    C --> D[4. Demonstration]
    D --> E[5. Evaluation]
    E --> F[6. Communication]
    F --> A

    A1[Literature review\nProblem statement\nStakeholder consultation] --> A
    B1[Research objectives\nSO1-SO5] --> B
    C1[Requirements\nArchitecture\nImplementation] --> C
    D1[Test corpus\nBoard minutes analysis] --> D
    E1[Metrics\nExpert review\nUser feedback] --> E
    F1[Thesis\nReport\nPresentation] --> F
```

## Figure 3.2 - Overall System Architecture

```mermaid
flowchart TB
    subgraph P[Presentation Layer]
        UI[React Dashboard]
        UP[Upload Interface]
        QP[Query Panel]
        RP[Reports & Export]
        ST[Settings / Admin]
    end

    subgraph A[Application Layer]
        API[Flask REST API]
        AUTH[JWT Authentication]
        ORCH[Analysis Orchestrator]
    end

    subgraph M[Processing & AI Layer]
        EXT[Document Extraction]
        PRE[Preprocessing Engine]
        EMB[Embedding Generator]
        RET[RAG Retriever]
        LLM[LLM / Zero-shot Engine]
        SENT[Sentiment Module]
        TREND[Longitudinal Analyzer]
    end

    subgraph S[Storage Layer]
        DB[(SQLite / PostgreSQL)]
        VDB[(Vector Index)]
        LOG[(Audit Logs)]
    end

    UI --> API
    UP --> API
    QP --> API
    RP --> API
    ST --> API

    API --> AUTH
    API --> ORCH
    ORCH --> EXT
    EXT --> PRE
    PRE --> EMB
    EMB --> VDB
    PRE --> DB
    ORCH --> RET
    RET --> VDB
    RET --> LLM
    LLM --> DB
    LLM --> SENT
    SENT --> DB
    TREND --> DB
    ORCH --> TREND
    API --> LOG
```

## Figure 3.3 - Use Case Diagram

```mermaid
flowchart LR
    GA[Governance Analyst]
    BS[Board Secretary]
    SA[System Administrator]

    subgraph SYS[LLM-Powered Board Minute Analysis System]
        UC1((Upload Document))
        UC2((Trigger Analysis))
        UC3((View Trend Dashboard))
        UC4((Query Corpus))
        UC5((Export Report))
        UC6((Manage Themes))
        UC7((Adjust Thresholds))
    end

    GA --> UC2
    GA --> UC3
    GA --> UC4
    GA --> UC5

    BS --> UC1
    BS --> UC3
    BS --> UC5

    SA --> UC6
    SA --> UC7
    SA --> UC5
```

## Figure 3.4 - Document Ingestion and Preprocessing Flow

```mermaid
flowchart TD
    S[Start] --> U[Upload PDF / DOCX / TXT / Image]
    U --> D{Detect File Format}
    D -->|Digital PDF| P1[Extract Text with PyPDF2 / pdfplumber]
    D -->|DOCX| P2[Extract Text with python-docx]
    D -->|Scanned PDF / Image| P3[OCR with Tesseract]

    P1 --> C[Clean and Normalize Text]
    P2 --> C
    P3 --> C

    C --> M[Extract Metadata\nDate, Meeting No., Attendees]
    M --> N[Named Entity Recognition\nPII Anonymization]
    N --> G[Segment into Semantic Chunks]
    G --> E[Generate Embeddings]
    E --> V[Insert into Vector Store]
    E --> R[Persist Segment Records]
    V --> T[Trigger Thematic Analysis]
    R --> T
    T --> F[Return Results to Frontend]
    F --> X[End]
```

## Figure 3.5 - LLM Thematic Extraction Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant UI as Frontend Dashboard
    participant API as Flask API
    participant RET as Retriever
    participant VDB as Vector Store
    participant LLM as LLM / Zero-shot Engine
    participant DB as Database

    User->>UI: Submit query or request analysis
    UI->>API: POST /api/query or /api/analysis
    API->>RET: Retrieve relevant chunks
    RET->>VDB: Semantic similarity search
    VDB-->>RET: Top-k matching segments
    RET-->>API: Retrieved context
    API->>LLM: Prompt + retrieved context
    LLM-->>API: JSON themes, sentiment, evidence
    API->>DB: Store outputs and provenance
    API-->>UI: Return structured results
    UI-->>User: Display themes, trends, citations
```

## Figure 3.6 - ER Diagram

```mermaid
erDiagram
    USERS ||--o{ DOCUMENTS : uploads
    DOCUMENTS ||--o{ SEGMENTS : contains
    SEGMENTS ||--o{ EMBEDDINGS : has
    SEGMENTS ||--o{ SENTIMENT : has
    SEGMENTS ||--o{ SEGMENT_THEMES : classified_as
    THEMES ||--o{ SEGMENT_THEMES : assigned_to
    USERS ||--o{ AUDIT_LOG : generates

    USERS {
        string user_id PK
        string username
        string email
        string password_hash
        string role
        datetime created_at
    }

    DOCUMENTS {
        string document_id PK
        string source_file
        date meeting_date
        string uploader_id FK
        float extraction_confidence
        datetime created_at
    }

    SEGMENTS {
        string segment_id PK
        string document_id FK
        int chunk_index
        text original_text
        text cleaned_text
        int char_start
        int char_end
    }

    EMBEDDINGS {
        string embedding_id PK
        string segment_id FK
        string model_name
        blob vector_blob
        datetime created_at
    }

    THEMES {
        string theme_id PK
        string theme_name
        text description
        bool is_active
    }

    SEGMENT_THEMES {
        int association_id PK
        string segment_id FK
        string theme_id FK
        float confidence
        string source_model
        datetime analysis_ts
    }

    SENTIMENT {
        string sentiment_id PK
        string segment_id FK
        float vader_score
        float vader_compound
        string llm_sentiment
        datetime sentiment_ts
    }

    AUDIT_LOG {
        int log_id PK
        string user_id FK
        string action
        string resource
        datetime timestamp
        json details
    }
```

## Figure 3.7 - Class Diagram for Core Processing Components

```mermaid
classDiagram
    class DocumentIngestionPipeline {
        +ingest_document(filepath, document_id)
        +_extract_text(filepath)
        +_clean_text(raw_text)
        +_anonymize_text(text)
        +_chunk_text(text)
        +_persist_segments(document_id, segments, embeddings)
    }

    class ThematicAnalysisEngine {
        +analyze_segment(segment_text, segment_id, use_rag)
        +_rag_refine(segment_text, top_k)
        +_compute_sentiment(text)
        +discover_themes_unsupervised(all_segment_embeddings)
    }

    class TrendAnalyzer {
        +aggregate_by_period(theme_id, period)
        +compute_moving_average(series)
        +detect_trends(series)
    }

    class ApiService {
        +upload_document()
        +query_corpus()
        +get_trends()
        +export_report()
    }

    class VectorStore {
        +add(vector, metadata)
        +search(query_vector, top_k)
    }

    class RelationalDatabase {
        +insert_document()
        +insert_segment()
        +insert_theme()
        +save_analysis()
        +save_sentiment()
    }

    DocumentIngestionPipeline --> VectorStore
    DocumentIngestionPipeline --> RelationalDatabase
    ThematicAnalysisEngine --> VectorStore
    ThematicAnalysisEngine --> RelationalDatabase
    TrendAnalyzer --> RelationalDatabase
    ApiService --> DocumentIngestionPipeline
    ApiService --> ThematicAnalysisEngine
    ApiService --> TrendAnalyzer
```

## Figure 3.8 - Longitudinal Analysis Workflow

```mermaid
flowchart LR
    A[Stored Segment Themes] --> B[Group by Meeting Date]
    B --> C[Aggregate by Semester / Academic Year]
    C --> D[Compute Theme Frequency]
    C --> E[Compute Average Sentiment]
    D --> F[Trend Detection\nMoving Average / Mann-Kendall]
    E --> F
    F --> G[Store in ThemeTimeSeries]
    G --> H[Render Dashboard Charts]
```

## Figure 3.9 - Dashboard Interaction Flow

```mermaid
flowchart TD
    A[User Logs In] --> B[Role-Based Navigation]
    B --> C[View KPI Summary]
    B --> D[Upload Documents]
    B --> E[Explore Trends]
    B --> F[Search Corpus]
    B --> G[Generate Reports]
    E --> H[Filter by Theme / Date Range]
    F --> I[Open Evidence-Backed Result]
    G --> J[Download CSV / PDF / JSON]
```

## Figure 3.10 - RAG Query Processing Flow

```mermaid
flowchart TD
    Q[User Question] --> QE[Encode Query Embedding]
    QE --> RS[Retrieve Top-k Similar Segments]
    RS --> CTX[Construct Context Window]
    CTX --> PR[Build Prompt Template]
    PR --> LM[LLM Response Generation]
    LM --> JS[Parse Structured JSON]
    JS --> OUT[Return Answer with Citations]
```

## Suggested Caption Style

- Figure 3.1 - DSR Process Model for the Study
- Figure 3.2 - Overall Architecture of the LLM-Powered Board Minute Analysis Framework
- Figure 3.3 - Use Case Diagram for Core Users and System Functions
- Figure 3.4 - Document Ingestion and Preprocessing Pipeline
- Figure 3.5 - Sequence Diagram of LLM-Based Thematic Extraction and RAG Querying
- Figure 3.6 - Entity-Relationship Diagram of the System Database
- Figure 3.7 - Class Diagram of Core Processing Modules
- Figure 3.8 - Workflow for Longitudinal Trend Analysis
- Figure 3.9 - Dashboard Interaction Flow
- Figure 3.10 - Retrieval-Augmented Generation Query Flow
