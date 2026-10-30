# SQL Copilot LinkedIn launch post

I am excited to share **SQL Copilot** - a production-ready workspace that turns business questions into reviewed, read-only SQL.

The goal was to make data exploration faster without losing the business context, schema awareness, validation, or traceability needed to trust a result.

## What SQL Copilot does

- Translates plain-language business questions into SQL across associates, clients, projects, delivery activity, invoices, payments, departments, and employees.
- Uses schema-aware retrieval: business vocabulary, table and column mapping, relationship linking, join-path planning, and SQL examples are combined before a query is prepared.
- Supports hybrid RAG retrieval with local keyword/BM25 search and optional vector/FAISS retrieval when embeddings are enabled.
- Uses the NVIDIA Nemotron 3.5 Lightning LLM API for structured reasoning and SQL generation when model assistance is needed.
- Runs a seven-stage multi-agent workflow: request intake, intent analysis, data matching, query planning, SQL generation, validation and scoring, then an explainable response.
- Validates read-only SQL, known schema objects, statement scope, join and coverage rules before presenting the answer.
- Maintains short conversational context and a query cache so repeated requests can return faster while preserving recent user intent.
- Provides an explainability view with confidence, agent scorecard, workflow stages, selected data, and refinements.
- Includes SQL Repair for syntax correction and database connection troubleshooting, with corrected SQL and practical diagnostics.
- Supports account creation, password recovery through a security question, responsive mobile behavior, and accessible light and dark themes.

## Deployment architecture

- **Frontend:** Next.js, OpenNext, and Cloudflare.
- **Public URL:** Cloudflare Pages at https://sql-copilot.pages.dev
- **Backend:** Flask/ASGI with Uvicorn and Docker on an Oracle Cloud VM.
- **Model integration:** NVIDIA API for Nemotron 3.5 Lightning structured chat completions.
- **Security:** authenticated sessions, CSRF protection, strict CORS origins, and read-only SQL policy checks.

Try it live: https://sql-copilot.pages.dev

Explore the source: https://github.com/shasanksingh/sql-copilot

I would love to hear how your team approaches trusted natural-language access to business data.

#SQL #DataAnalytics #BusinessIntelligence #DataEngineering #RAG #LLM #MultiAgentSystems #NVIDIA #Cloudflare #OracleCloud #DeveloperTools

---

## LinkedIn carousel upload steps

1. Download `output/pdf/sql-copilot-linkedin-product-walkthrough.pdf`.
2. In LinkedIn, choose **Start a post** and select **Document**.
3. Upload the PDF and set the title to `SQL Copilot: from business question to reviewed SQL`.
4. Paste the launch post above into the post text.
5. Confirm this sequence: architecture, light account setup, light dashboard, schema explorer, relationship graph, SQL Copilot with explainability, SQL Repair, closing slide.
6. Confirm the live and source links are present, preview the document, and publish.

The carousel uses a light-theme, landscape product walkthrough. The opening architecture slide shows the complete data, retrieval, multi-agent, validation, and execution flow. The SQL Copilot slide includes the explainability panel with confidence, scorecard, and workflow stages.
