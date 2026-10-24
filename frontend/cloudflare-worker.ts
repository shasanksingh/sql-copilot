// @ts-expect-error: The OpenNext worker is generated immediately before Wrangler bundles this entrypoint.
import nextWorker from "./.open-next/worker.js";

type WorkerExecutionContext = {
  waitUntil(promise: Promise<unknown>): void;
};

export interface Env {
  API_ORIGIN?: string;
}

const API_PREFIXES = [
  "/auth/",
  "/schema/",
  "/metadata/",
  "/enterprise-schema",
  "/schema-requests",
  "/schema-request",
  "/feedback",
  "/logs/",
  "/sql",
  "/metrics",
  "/health",
  "/runtime/",
  "/diagnostics/"
];

function isApiRequest(pathname: string) {
  return API_PREFIXES.some((prefix) => {
    if (pathname === prefix) return true;
    return prefix.endsWith("/")
      ? pathname.startsWith(prefix)
      : pathname.startsWith(`${prefix}/`);
  });
}

function configuredOrigin(value?: string) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") return null;
    return url;
  } catch {
    return null;
  }
}

async function proxyToApi(request: Request, env: Env) {
  const upstreamOrigin = configuredOrigin(env.API_ORIGIN);
  if (!upstreamOrigin) {
    return Response.json(
      { error: "The production API is not configured. Set the API_ORIGIN Worker secret to the HTTPS Flask backend URL." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(`${incomingUrl.pathname}${incomingUrl.search}`, upstreamOrigin);
  const headers = new Headers(request.headers);
  headers.set("X-Forwarded-Host", incomingUrl.host);
  headers.set("X-Forwarded-Proto", incomingUrl.protocol.replace(":", ""));
  headers.delete("host");

  return fetch(new Request(upstreamUrl, {
    method: request.method,
    headers,
    body: request.body,
    redirect: "manual"
  }));
}

const worker = {
  async fetch(request: Request, env: Env, ctx: WorkerExecutionContext) {
    if (isApiRequest(new URL(request.url).pathname)) {
      return proxyToApi(request, env);
    }
    return nextWorker.fetch(request, env, ctx);
  }
};

export default worker;
