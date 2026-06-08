# AI Email CRM Project - Requirements

## 1. Project Overview
This project is an AI-powered CRM system that automatically processes emails, converts them into structured documents, analyzes them using AI, and identifies sales opportunities using BANT (Budget, Authority, Need, Timeline) model.

---

## 2. Core Modules

### 2.1 Authentication Module
- User registration
- User login
- User logout
- JWT-based session management
- Get current user profile

---

### 2.2 Project Module
- Create project
- List all projects
- Update project details
- Delete project

Each project represents a workspace for email processing.

---

### 2.3 Document (Email) Module
- Fetch and store emails in database
- List documents per project
- View single document
- Mark document as closed
- Delete document

Each document represents a single email.

---



### 2.4 Metadata Module
- Store AI-generated insights:
  - sentiment
  - BANT fields
  - confidence score
- Store structured analysis data per email

---

## 3. Database Entities

- Users
- Projects
- Documents (Emails)
- Metadata (AI analysis)

---

## 4. API Modules

### Auth APIs
- POST /auth/register
- POST /auth/login
- POST /auth/logout
- GET /auth/me

### Project APIs
- POST /projects
- GET /projects
- PATCH /projects/{id}
- DELETE /projects/{id}

### Document APIs
- GET /projects/{id}/documents
- GET /documents/{id}
- PATCH /documents/{id}
- DELETE /documents/{id}

---

## 5. Background Jobs

- Email fetching (scheduled job)
- AI processing pipeline
- Opportunity detection

---

## 6. Tech Stack (Suggested)

- Backend: FastAPI
- Database: PostgreSQL
- Queue: Celery / Redis
- AI: LLM API (OpenAI / Claude)
- Email: Gmail API
- PDF generation: ReportLab / WeasyPrint

---

## 7. System Flow

User Email → Email Fetcher → Database → AI Processing → BANT Analysis → Opportunity Creation → Dashboard

---

## 8. Future Enhancements

- Multi-email provider support
- Team collaboration
- Advanced CRM dashboard
- Email reply automation
- Sales forecasting model