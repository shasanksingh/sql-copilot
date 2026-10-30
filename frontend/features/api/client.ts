import type {
  AuthResponse,
  CopilotResponse,
  EnterpriseSchemaResponse,
  ErResponse,
  HealthResponse,
  MetadataStatusResponse,
  MetricsResponse,
  MetricsRange,
  RelationshipResponse,
  SchemaCatalogResponse,
  SchemaStudioResponse,
  SchemaStudioTablePayload,
  SchemaRequest,
  SchemaRequestsResponse,
  FeedbackItem,
  ForgotPasswordResponse,
  ConfigureProviderPayload,
  ConfigureProviderResponse,
  RuntimeConfigResponse,
  ConfigureEmailPayload,
  ConfigureEmailResponse,
  SqlRepairResponse
} from "./types";
import type { SqlLanguage } from "@/lib/sql-language";

const CONFIGURED_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isLoopback(hostname: string) {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function apiBase() {
  if (typeof window === "undefined") {
    return CONFIGURED_API_BASE ?? "http://127.0.0.1:5000";
  }
  if (!CONFIGURED_API_BASE) {
    if (!isLoopback(window.location.hostname)) {
      throw new Error(
        "Production API URL is not configured. Set NEXT_PUBLIC_API_BASE_URL to the HTTPS API URL served by the Cloudflare Worker and rebuild the frontend."
      );
    }
    return `${window.location.protocol}//${window.location.hostname}:5000`;
  }
  try {
    const configured = new URL(CONFIGURED_API_BASE);
    if (isLoopback(configured.hostname) && isLoopback(window.location.hostname)) {
      configured.hostname = window.location.hostname;
    }
    // The production Worker proxies API paths on the same hostname as the
    // frontend. When the app is reached through a Pages proxy or a custom
    // domain, keep authentication cookies first-party by using that hostname
    // instead of the Worker deployment hostname embedded at build time.
    if (!isLoopback(configured.hostname) && window.location.origin !== configured.origin) {
      return window.location.origin;
    }
    return configured.toString().replace(/\/$/, "");
  } catch {
    return CONFIGURED_API_BASE;
  }
}

function csrfToken() {
  if (typeof document === "undefined") return "";
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith("sql_copilot_csrf="));
  return match ? decodeURIComponent(match.split("=", 2)[1]) : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const headers = new Headers(init?.headers);
  if (!isFormData && init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (["POST", "PATCH", "PUT", "DELETE"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  let response: Response;
  const base = apiBase();
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      credentials: "include",
      headers
    });
  } catch {
    throw new Error(
      `Cannot connect to the SQL Copilot API at ${base}. Start the backend and verify that this frontend origin is allowed.`
    );
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    try {
      const parsed = JSON.parse(body) as { error?: string; code?: string; message?: string };
      throw new ApiError(
        parsed.error || parsed.message || `API request failed: ${response.status}`,
        response.status,
        parsed.code
      );
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(body || `API request failed: ${response.status}`, response.status);
    }
  }

  return response.json() as Promise<T>;
}

export function generateSql(query: string, language: SqlLanguage = "sql") {
  return request<CopilotResponse>("/sql", {
    method: "POST",
    body: JSON.stringify({ query, language })
  });
}

export function repairSql(payload: { statement: string; errorMessage?: string; language: SqlLanguage }) {
  return request<SqlRepairResponse>("/sql/repair", {
    method: "POST",
    body: JSON.stringify({
      statement: payload.statement,
      error_message: payload.errorMessage ?? "",
      language: payload.language
    })
  });
}

export function getRelationships() {
  return request<RelationshipResponse>("/schema/relationships");
}

export function getSchemaCatalog() {
  return request<SchemaCatalogResponse>("/schema/catalog");
}

export function getMetadataStatus() {
  return request<MetadataStatusResponse>("/metadata/status");
}

export function refreshMetadata() {
  return request<{ status: MetadataStatusResponse["status"] }>("/metadata/refresh", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function createSchemaStudioTable(payload: SchemaStudioTablePayload) {
  return request<SchemaStudioResponse>("/schema/studio/tables", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateSchemaStudioTable(tableName: string, payload: SchemaStudioTablePayload) {
  return request<SchemaStudioResponse>(`/schema/studio/tables/${encodeURIComponent(tableName)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteSchemaStudioTable(tableName: string) {
  return request<SchemaStudioResponse>(`/schema/studio/tables/${encodeURIComponent(tableName)}`, {
    method: "DELETE"
  });
}

export function applySchemaRequest(requestId: number) {
  return request<SchemaStudioResponse>(`/schema/studio/apply-request/${requestId}`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function getEnterpriseSchema() {
  return request<EnterpriseSchemaResponse>("/enterprise-schema");
}

export function getSchemaRequests() {
  return request<SchemaRequestsResponse>("/schema-requests");
}

export function createSchemaRequest(payload: {
  request_kind: string;
  table_name: string;
  business_purpose: string;
  columns: string[];
  relationships: string;
  sample_data: string;
  business_rules: string;
  file?: File;
}) {
  const formData = new FormData();
  Object.entries(payload).forEach(([key, value]) => {
    if (key === "file") return;
    formData.set(key, Array.isArray(value) ? value.join(",") : String(value));
  });
  if (payload.file) formData.set("file", payload.file);
  return request<SchemaRequest>("/schema-request", {
    method: "POST",
    body: formData
  });
}

export function updateSchemaRequestStatus(requestId: number, status: SchemaRequest["status"]) {
  return request<SchemaRequest>(`/schema-request/${requestId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status })
  });
}

export function signup(payload: {
  name: string;
  email: string;
  password: string;
  security_question: string;
  security_answer: string;
  remember?: boolean;
}) {
  return request<AuthResponse>("/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function login(payload: { email: string; password: string; remember: boolean }) {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getCurrentUser() {
  return request<AuthResponse>("/auth/me");
}

export function saveSecurityQuestion(payload: { security_question: string; security_answer: string }) {
  return request<AuthResponse & { message: string }>("/auth/security-question", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function logout() {
  return request<{ status: string }>("/auth/logout", { method: "POST" });
}

export function forgotPassword(email: string, securityAnswer?: string) {
  return request<ForgotPasswordResponse>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email, security_answer: securityAnswer })
  });
}

export function resetPassword(token: string, password: string) {
  return request<{ message: string }>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password })
  });
}

export function createFeedback(category: string, message: string) {
  return request<FeedbackItem>("/feedback", {
    method: "POST",
    body: JSON.stringify({ category, message })
  });
}

export function getFeedback() {
  return request<{ feedback: FeedbackItem[] }>("/feedback");
}

export function logFrontendError(payload: {
  event: string;
  level?: "info" | "warning" | "error";
  message: string;
  path?: string;
  stack?: string;
}) {
  return request<void>("/logs/frontend", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getErDiagram() {
  return request<ErResponse>("/schema/er");
}

export function getMetrics(range?: MetricsRange["key"]) {
  const suffix = range ? `?range=${encodeURIComponent(range)}` : "";
  return request<MetricsResponse>(`/metrics${suffix}`);
}

export function getHealth() {
  return request<HealthResponse>("/health");
}

export function getRuntimeConfig() {
  return request<RuntimeConfigResponse>("/runtime/config");
}

export function configureProvider(payload: ConfigureProviderPayload) {
  return request<ConfigureProviderResponse>("/runtime/provider/configure", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function configureEmail(payload: ConfigureEmailPayload) {
  return request<ConfigureEmailResponse>("/runtime/email/configure", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
