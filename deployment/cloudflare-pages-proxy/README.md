# SQL Copilot Pages hostname

This small Cloudflare Pages project proxies the production OpenNext Worker.
It exists so an external DNS provider can safely CNAME a custom hostname to
`sql-copilot.pages.dev`, while the application continues to use the existing
production Worker and Oracle API.

Deploy it from this directory:

```powershell
npx wrangler pages deploy public --project-name sql-copilot
```

For an `is-a.dev` registration, use this exact CNAME target after confirming
the Pages deployment:

```json
{
  "owner": {
    "username": "shasanksingh"
  },
  "records": {
    "CNAME": "sql-copilot.pages.dev"
  }
}
```

After the registration pull request is merged, add `sql-copilot.is-a.dev` as a
custom domain to the Pages project using the `is-a.dev` Cloudflare Pages guide.
Then append `https://sql-copilot.is-a.dev` to `FRONTEND_ORIGINS` on Oracle and
restart the API container so credentialed requests are allowed from the new
origin.
