# SQL Copilot LinkedIn launch post

I am excited to share **SQL Copilot** - a production-ready workspace for turning business questions into reviewed, read-only SQL.

The goal was simple: make business data easier to explore without losing the context, safeguards, or visibility needed to trust the result.

## What it does

- Turns plain-language questions into SQL across business data such as associates, clients, projects, delivery activity, invoices, payments, departments, and employees.
- Grounds every request in a schema-aware retrieval flow, business vocabulary, relationships, and SQL validation rules.
- Runs a seven-stage multi-agent workflow: understand the request, resolve business terms, match relevant data, plan the query, prepare SQL, review and refine, then prepare the response.
- Uses the NVIDIA Nemotron 3.5 Lightning LLM API for structured generation when a request benefits from model reasoning.
- Keeps repeat questions fast with short-term conversation context and query caching.
- Produces safe contextual drafts when a requested attribute is not mapped in the schema, instead of presenting an invented field as verified SQL.
- Includes an explainability panel with confidence, review scorecard, and the seven workflow stages for every generated result.
- Includes SQL Repair for syntax issues and common database connection errors, with corrected SQL and useful troubleshooting guidance.
- Provides account creation, sign-in, password recovery with a security question, responsive mobile views, and accessible light and dark themes.

## How it is deployed

- Frontend: Next.js on Cloudflare Workers, with a Cloudflare Pages hostname for the custom-domain path.
- API: Flask and Uvicorn on Oracle Cloud.
- Security: authenticated sessions, CSRF protection, read-only SQL validation, and a strict frontend CORS allowlist.

Try it live: https://sql-copilot.pages.dev

View the source: https://github.com/shasanksingh/sql-copilot

I would love to hear what would make a natural-language-to-SQL workflow useful for your team.

#SQL #DataAnalytics #BusinessIntelligence #DataEngineering #Cloudflare #OracleCloud #NVIDIA #DeveloperTools

---

## LinkedIn carousel upload steps

1. Download `output/pdf/sql-copilot-linkedin-carousel-light.pdf` from this project.
2. In LinkedIn, select **Start a post** and then choose the **Document** option.
3. Upload the PDF, enter `SQL Copilot: from business question to reviewed SQL` as the document title, and paste the launch post above into the post text.
4. Confirm the slides are in this sequence: introduction, light query review, light SQL Repair, closing slide.
5. Add the live and GitHub links to the post body, review the document preview, then publish.

The carousel uses landscape, light-theme production screenshots only. The query-review slide is the explainability snapshot: it includes confidence, the review scorecard, and the visible multi-stage workflow.
