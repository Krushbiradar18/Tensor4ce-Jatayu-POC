# Jatayu Credit Risk Frontend

## Overview

This is the Vite + React frontend for the Jatayu credit risk assessment system.

The application currently:
- shows applicant rows from PostgreSQL-backed backend APIs
- lets users submit credit risk assessments
- displays persisted processed results from the backend database
- renders detailed result panels and full report views

The frontend no longer depends on mock frontend-only history data.

## Stack

- React 18
- Vite
- React Router
- Axios
- TailwindCSS
- Lucide React

## Project Structure

```text
credit_frontend/
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── App.jsx
    ├── main.jsx
    ├── index.css
    ├── components/
    ├── pages/
    │   ├── ApplicationHistory.jsx
    │   ├── Dashboard.jsx
    │   └── ReportPage.jsx
    └── services/
        └── api.js
```

## Prerequisites

- Node.js 18+ recommended
- npm
- Backend running on FastAPI

## Install

From the workspace root:

```powershell
cd credit_frontend
npm install
```

## Environment Variables

Create a `.env` file inside `credit_frontend` if you want to override the API URL.

Example:

```env
VITE_API_BASE_URL=http://localhost:8000
```

If not set, the frontend defaults to:

```text
http://localhost:8000
```

## Run the Frontend

```powershell
cd credit_frontend
npm run dev
```

Vite will print the local dev URL, typically:

```text
http://localhost:5173
```

## Backend Requirements

The frontend expects the backend to be running and serving these endpoints:

- `GET /health`
- `GET /db/users`
- `POST /db/users`
- `GET /db/processed`
- `GET /db/processed/{pan}`
- `GET /user/{pan}`
- `POST /assess-risk`
- `GET /model/info`

## Current Frontend Behavior

### Application History

The application history page now loads data from the backend database:
- applicant rows come from `GET /db/users`
- processed results come from `GET /db/processed`
- after a successful submit, only the updated row is rehydrated via `GET /db/processed/{pan}`

### Risk Assessment Submission

When a user clicks Submit:
1. frontend sends `POST /assess-risk`
2. backend computes the result and persists it to `risk_processed`
3. frontend fetches `GET /db/processed/{pan}`
4. UI updates the single row with the canonical DB-saved result

## Useful Commands

### Development server

```powershell
npm run dev
```

### Production build

```powershell
npm run build
```

### Preview production build

```powershell
npm run preview
```

## Main Files

- `src/pages/ApplicationHistory.jsx`
  - DB-backed applications table and expanded result panel
- `src/pages/ReportPage.jsx`
  - detailed full report view
- `src/services/api.js`
  - all backend API methods

## Troubleshooting

### `vite is not recognized`

Install dependencies first:

```powershell
npm install
```

### Frontend loads but no rows appear

Check:
- backend is running
- `VITE_API_BASE_URL` points to the correct backend
- `GET /db/users` returns data

### Processed row does not update after submit

Check:
- `POST /assess-risk` returns 200
- backend writes to `risk_processed`
- `GET /db/processed/{pan}` returns the stored result

## Integration Notes

This frontend is now coupled to the real backend API shape currently implemented in `credit_backend`.
It is no longer documented as a mock-only UI.
