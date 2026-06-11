import type { CopilotResponse, ErResponse, HealthResponse, MetricsResponse, RelationshipResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:5000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(body || `API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function generateSql(query: string) {
  return request<CopilotResponse>("/sql", {
    method: "POST",
    body: JSON.stringify({ query })
  });
}

export function getRelationships() {
  return request<RelationshipResponse>("/schema/relationships");
}

export function getErDiagram() {
  return request<ErResponse>("/schema/er");
}

export function getMetrics() {
  return request<MetricsResponse>("/metrics");
}

export function getHealth() {
  return request<HealthResponse>("/health");
}
