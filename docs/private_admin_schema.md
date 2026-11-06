# Confidential Administrator Schema

The administrator schema vault keeps business-only table definitions outside the repository and outside ordinary user sessions. It is intended for restricted domains such as custody positions, movements, blocks, and portfolio-balance calculations.

## Storage and source control

- Source screenshots under `Custody Schema/` are ignored by Git.
- The normalized catalog is stored at `.runtime/private-schema/catalog.json` by default.
- Its generated embedding index is stored beside it as `catalog.embeddings.json`.
- Administrator planning state uses `.runtime/sqlite/private_sql_agent_feedback.sqlite`.
- Oracle Compose persists these files through the `deployment/oracle/runtime:/app/.runtime` volume.

Do not move the screenshots, catalog, embedding index, passwords, or private planner database into a tracked directory.

## Access boundary

- Only authenticated accounts with `role=admin` can open `/admin` or call `/admin/private-schema*`.
- Ordinary `/schema/catalog`, `/schema/relationships`, and `/schema/er` responses exclude private objects.
- Administrator schema responses merge public and private objects only for that administrator session.
- Disabling or changing account roles revokes access according to the auth store, and the final active administrator cannot be removed.
- Private administrator prompts bypass shared query traces and public analytics.

## Retrieval and model policy

The vault builds a deterministic 384-dimensional feature-hash/cosine index on the server. No embedding text is sent to a remote API.

Remote language-model use is blocked by default:

```text
PRIVATE_SCHEMA_ALLOW_REMOTE_LLM=0
```

Set it to `1` only after the data owner approves the configured provider for confidential prompts and schema context. The Admin Console displays whether remote model access is blocked or approved.

## Import and reindex

Sign in as an administrator and open `/admin`:

1. Select a validated JSON catalog in **Confidential schema vault**.
2. Import it. The backend validates table names, columns, relationships, and limits before replacing the runtime catalog.
3. Use **Reindex** after a catalog change.
4. Test retrieval with a business phrase such as `available position balance by portfolio`.

The current runtime catalog supports direct full-detail requests with `SELECT *`, monthly movement aggregation using `security_movement.trade_date`, and the governed formula:

```text
available_balance = settled_balance - active_blocked_balance
```

The balance path joins portfolio ownership, position keys, signed security movements, and blocks active as of the requested balance date.

## Production environment

```text
PRIVATE_SCHEMA_FILE=/app/.runtime/private-schema/catalog.json
PRIVATE_AGENT_FEEDBACK_DB_PATH=/app/.runtime/sqlite/private_sql_agent_feedback.sqlite
PRIVATE_SCHEMA_ALLOW_REMOTE_LLM=0
```

Create the initial administrator with `BOOTSTRAP_ADMIN_*` values in the server-only runtime secret file. Remove or rotate the bootstrap password after first login. Never place these values in frontend variables or a committed environment file.
