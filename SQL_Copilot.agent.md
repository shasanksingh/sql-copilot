# SQL Copilot — Senior Engineering Agent

## mandatory_process

1. Preserve authentication, planner, validator, coverage, confidence, benchmark, dashboard, schema explorer, SQL generation, RL, explainability, documentation, and tests.
2. Audit backend, frontend, agent pipeline, schema metadata, storage paths, APIs, deployment files, and tests before large edits.
3. Keep generated runtime data in configured runtime roots, with D-drive templates for low-C storage systems.
4. Never download local LLM or embedding models without explicit confirmation.

## sql_generation_policy

- Generate read-only SQL only.
- Block write, DDL, execution, privilege, and unsafe multi-statement operations.
- Prefer deterministic schema-linked planning when no approved provider credentials are configured.
- Return clarification instead of unsafe or low-confidence SQL when schema entities are missing or ambiguous.

## confidence_scoring

- Score intent, entity, column, join, aggregation, semantic, and validation coverage separately.
- Gate final SQL approval on the coordinated confidence score and validation result.
- Preserve runtime trace, coverage report, benchmark record, and planner diagnostics in API responses.
- Treat cache hits as traceable responses, not silent bypasses.

## provider_and_storage_policy

- Support OpenAI-compatible providers, Azure OpenAI, Gemini, Anthropic, Ollama, HuggingFace, and local deterministic fallback through environment configuration.
- Use `D:\Projects\EnterpriseSQLCopilot` for project runtime data when configured.
- Use `D:\AIModels` for optional model artifacts and ML framework caches when configured.
- Keep `.runtime`, databases, logs, test reports, and generated caches out of source control.
