# Backend Architecture

The backend now lives in `backend/` while the root `main.py` remains a compatibility shim.

```text
backend/
  app.py                   Flask app, CORS, schema loading, SQL routes, metrics
  main.py                  ASGI exports for uvicorn
  data/RAG_DOC.xlsx        schema source
  static/index.html        legacy UI served at /legacy
  requirements.txt         Python runtime dependencies
  requirements-rl.txt      optional RL dependencies
```

## Entrypoints

```bash
uvicorn main:asgi_app --host 127.0.0.1 --port 5000
uvicorn backend.main:asgi_app --host 127.0.0.1 --port 5000
```

## Runtime Paths

- Schema file: `backend/data/RAG_DOC.xlsx`, override with `SCHEMA_FILE`.
- Feedback DB: `backend/sql_agent_feedback.sqlite`, override with `AGENT_FEEDBACK_DB_PATH`.
- FAISS cache: `backend/.cache/`.
- RL model: `rl/models/sql_ppo_agent.zip`, override with `RL_MODEL_PATH`.

## Production Notes

- `/` returns API metadata.
- `/legacy` serves the old HTML UI for reference only.
- The Next.js app in `frontend/` is the production UI.
- Add authentication, database connection management, and a safe read-only execution endpoint before connecting production databases.
