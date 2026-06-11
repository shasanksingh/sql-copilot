# SQL Copilot

Premium AI SaaS workspace for natural-language SQL generation, schema exploration, explainable query planning, and SQL optimization.

The project is now split into a modern production frontend and a Python backend:

```text
.
├── backend/                 # Flask/ASGI SQL Copilot API
│   ├── app.py               # API routes, schema loading, SQL generation, metrics
│   ├── main.py              # backend ASGI entrypoint
│   ├── data/RAG_DOC.xlsx    # schema workbook
│   ├── static/              # legacy HTML kept only at /legacy
│   └── requirements.txt
├── frontend/                # Next.js 15 SaaS interface
│   ├── app/                 # App Router pages
│   ├── components/          # app shell, feature components, shadcn-style UI
│   ├── features/            # API, Zustand stores, shared demo data
│   └── package.json
├── agentic/                 # enterprise SQL planning and explainability agents
├── rl/                      # optional PPO feedback/optimization layer
├── tests/                   # backend/agent tests
├── docs/                    # architecture docs
└── main.py                  # compatibility shim for uvicorn main:asgi_app
```

## Frontend

Stack:

- Next.js 15 App Router
- React 19
- TypeScript
- Tailwind CSS
- shadcn/ui-style reusable components
- React Query
- Zustand
- Recharts
- React Flow
- Framer Motion

Pages:

- Dashboard with statistics cards, query analytics, recent activity, confidence and latency metrics
- SQL Copilot Chat with suggested prompts, history, SQL generation panel, explainability, and streaming-style loading states
- Schema Explorer with table search, column explorer, and relationship details
- Schema Graph with interactive zoom/pan relationship visualization
- Query Execution with SQL editor, preview result grid, CSV export, and Excel export
- Explainable AI panel with intent, entities, tables, columns, join path, confidence, and plan
- Query Planner visualizing table selection, join chain, filters, and aggregations
- SQL Optimizer with suggestions, missing index candidates, warnings, and risk meter
- Settings for connection details, query preferences, validation controls, and theme selection

## Backend

The backend keeps the existing Flask pipeline and exposes it through ASGI:

- `POST /sql`
- `GET /health`
- `GET /schema/relationships`
- `GET /schema/er`
- `GET /metrics`
- `GET /legacy` for the old static UI reference

It supports schema-aware retrieval, local LLM-free generation, optional remote LLM calls, SQL validation, confidence scoring, query cache, explainability, and RL feedback metrics.

## Run

Backend:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

Optional frontend env:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000
```

## Test

Backend:

```bash
python -m pytest tests
python -m py_compile main.py backend/app.py backend/main.py
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Notes

- The redesigned frontend is the primary UI. The old HTML file was moved to `backend/static/index.html` and is served only from `/legacy`.
- The root `main.py` remains as a compatibility shim, so existing `uvicorn main:asgi_app` commands still work.
- Generated artifacts are ignored via `.gitignore`, including `frontend/node_modules`, `frontend/.next`, and `backend/.cache`.
