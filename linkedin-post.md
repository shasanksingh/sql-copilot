# SQL Copilot — LinkedIn post draft

Shipping an end-to-end SQL workspace has been a rewarding build.

**SQL Copilot** turns a business question into reviewed, read-only SQL while keeping the decision path clear for the person using it.

What is now included:

- Schema-aware query generation across business data such as associates, customers, projects, invoices, delivery activity, and employees.
- A seven-stage workflow that understands the request, resolves business terms, finds relevant data, plans the query, prepares SQL, reviews it, and presents the result.
- NVIDIA Nemotron-powered structured generation, with schema grounding and validation before a query is presented.
- Safe contextual drafts when a request uses an attribute that is not yet mapped in the schema — no invented mapping is represented as verified SQL.
- SQL Repair for pasted syntax and connection errors, with corrected SQL and practical diagnostic guidance.
- Saved answers and short conversation context to make repeat work faster.
- Account creation, sign-in, recovery questions, responsive mobile layouts, and accessible light/dark themes.
- A production frontend on Cloudflare Workers and a Flask API on Oracle Cloud, connected through a strict CORS allowlist.

Live workspace: https://sql-copilot-frontend.singhshasank50.workers.dev

Source code: https://github.com/shasanksingh/sql-copilot

The next step is a free custom project domain: `sql-copilot.is-a.dev`.

What would make you trust a natural-language-to-SQL workflow in your day-to-day data work?

#SQL #DataAnalytics #BusinessIntelligence #DataEngineering #Cloudflare #OracleCloud #DeveloperTools
