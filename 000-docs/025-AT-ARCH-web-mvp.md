# 025-AT-ARCH — Web MVP Architecture

## Overview

Firebase-hosted web app where users log in, upload DXF/PDF files, chat with AI about edits, see visual before/after previews, and download the result. No install, no terminal.

## Architecture

```
[Firebase Hosting]          [Cloud Run]               [Vertex AI]
React SPA (Vite)    -->   FastAPI Backend   -->    Gemini 2.5 Flash
  - Firebase Auth           - /api/upload              (tool-use loop)
  - Drag-drop upload        - /api/plan
  - Chat interface          - /api/apply
  - Before/after preview    - /api/render
  - Download button         - /api/download
                            - Session mgmt (temp files)
                            - Reuses EXISTING pipeline modules
```

## Key Design Decisions

1. **No pipeline rewrite** — backend imports the same `dxf_reader`, `planner`, `validators`, `edit_engine`, `renderer`, `dxf_writer` used by the desktop app.
2. **Session-based** — each upload creates a temp dir in `/tmp/cad-sessions/{session_id}/` with original, working copy, and renders. Sessions expire after 2 hours.
3. **Firebase Auth** — email/password + Google sign-in. ID tokens validated server-side via `firebase-admin` SDK.
4. **Hand-written CSS** — no Bootstrap/Tailwind. 8px grid, CSS custom properties, dark mode via `prefers-color-scheme`.

## API Contract

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/health` | GET | No | Health check |
| `/api/upload` | POST | Yes | Accept DXF/PDF (multipart), return session_id + context |
| `/api/plan` | POST | Yes | Prompt + session_id -> ChangeSet + preview + validation |
| `/api/apply` | POST | Yes | session_id + selected ops -> apply changes |
| `/api/render` | GET | Yes | session_id -> PNG render (original/edited/diff) |
| `/api/download` | GET | Yes | session_id -> edited DXF file download |

## File Structure

```
web/
├── frontend/          # React app (Vite)
│   ├── src/
│   │   ├── components/  # Landing, Login, Workspace, ChatPanel, PreviewPanel, etc.
│   │   ├── hooks/       # useAuth, useSession
│   │   ├── lib/         # api.js (backend client), firebase.js (config)
│   │   └── styles/      # reset, variables, base, layout, components, utilities
│   └── ...
├── backend/           # FastAPI (Cloud Run)
│   ├── main.py        # Routes
│   ├── session.py     # Session management
│   ├── auth.py        # Firebase token validation
│   ├── Dockerfile
│   └── cloudbuild.yaml
├── firebase.json      # Hosting config + rewrites
└── .firebaserc        # Project config
```

## Deployment

- **Frontend:** `cd web/frontend && npm run build && firebase deploy --only hosting`
- **Backend:** `gcloud builds submit --config web/backend/cloudbuild.yaml .`
- **Local dev:** `npm run dev` (frontend :3000) + `uvicorn web.backend.main:app --port 8322` (backend)
