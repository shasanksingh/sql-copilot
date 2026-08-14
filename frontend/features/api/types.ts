export type CopilotInsights = {
  confidence: number;
  threshold: number;
  valid: boolean;
  validation: string;
  source: string;
  summary?: string;
  tables: string[];
  columns: string[];
  query_type: string;
  clarification_required?: boolean;
  clarification_options?: string[];
  intent?: Record<string, unknown>;
  entities?: Record<string, unknown>;
  selected_tables?: string[];
  join_path?: string[];
  plan?: Record<string, unknown> | null;
  optimizations?: string[];
  optimized_sql?: string;
  optimization_explanation?: string[];
  execution_plan?: string[];
  cost_reduction_percent?: number;
  index_suggestions?: string[];
  confidence_breakdown?: Record<string, number>;
  confidence_evidence?: ConfidenceEvidenceItem[];
  coverage_report?: Record<string, unknown>;
  agent_telemetry?: Record<string, unknown>;
  execution_trace?: Record<string, unknown>;
  runtime_metrics?: Record<string, unknown>;
  benchmark_record?: Record<string, unknown>;
  query_complexity?: string;
  confidence_band?: "LOW" | "MEDIUM" | "HIGH" | string;
  provider_status?: Record<string, unknown>;
  llm_trace?: Record<string, unknown>;
  model_confidence?: number;
  planner_confidence?: number;
  validator_confidence?: number;
  coverage_confidence?: number;
  llm_provider?: string;
  llm_model?: string;
  fallback_used?: boolean;
  fallback_reason?: string;
  repair_attempts?: number;
  cache_hit?: boolean;
  generic_sql?: boolean;
  generic_mode?: string;
  generic_warning?: string;
  spider_examples?: Array<Record<string, unknown>>;
};

export type ConfidenceEvidenceItem = {
  key: string;
  label: string;
  score?: number | null;
  applicable: boolean;
  status: "passed" | "warning" | "failed" | "not_applicable" | string;
  required?: string[];
  matched?: string[];
  missing?: string[];
  note?: string;
};

export type CopilotResponse = {
  query: string;
  sql: string;
  message: string;
  insights: CopilotInsights;
};

export type SchemaRelationship = {
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
};

export type RelationshipResponse = {
  tables: string[];
  relationships: Record<string, SchemaRelationship[]>;
};

export type ErResponse = {
  format: "mermaid";
  diagram: string;
};

export type FeedbackTrendPoint = {
  query: string;
  reward: number;
  execution_time: number;
  validation_status: string;
  timestamp: string;
  valid: boolean;
  confidence: number;
  planner_score: number;
  validator_score: number;
  intent_score: number;
  join_score: number;
  column_score?: number;
  aggregation_score?: number;
  semantic_score?: number;
  system_confidence?: number;
  coverage_confidence?: number;
  model_confidence?: number;
  provider?: string;
  model?: string;
  complexity?: string;
  fallback_used?: boolean;
  retry_count?: number;
  latency_ms?: number;
};

export type MetricsRange = {
  key: "day" | "week" | "month" | "quarter" | "year" | "all" | string;
  days: number | null;
  from?: string | null;
  to?: string | null;
};

export type LlmProviderStatus = {
  provider: string;
  model: string;
  adapter?: string;
  configured: boolean;
  available: boolean;
  status: string;
  base_url?: string;
  reason?: string;
};

export type LlmMetrics = {
  provider: string;
  model: string;
  configured: boolean;
  request_count: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  fallback_count: number;
  fallback_rate: number;
  average_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  token_usage: Record<string, number>;
  repair_attempts: number;
  provider_errors: Record<string, number>;
};

export type MetricsResponse = {
  total: number;
  average_reward: number;
  query_success_rate: number;
  sql_accuracy: number;
  planner_accuracy?: number;
  validator_precision?: number;
  confidence_reliability?: number;
  average_latency: number;
  trend: FeedbackTrendPoint[];
  range?: MetricsRange;
  agent_telemetry?: {
    intent_accuracy: number;
    planner_accuracy: number;
    validation_accuracy: number;
    optimization_accuracy: number;
    coverage_score: number;
    fallback_rate?: number;
    enterprise_success_rate?: number;
    missing_concepts: string[];
    trend: Array<Record<string, unknown>>;
  };
  schema_growth?: {
    total_requests: number;
    status_counts: Record<string, number>;
    most_requested_domains: Array<[string, number]>;
    pending_requests: number;
  };
  enterprise_schema?: {
    tables_count: number;
    relationships_count: number;
    domains_count: number;
    supported_scales: string[];
  };
  llm_provider?: LlmProviderStatus;
  llm_metrics?: LlmMetrics;
  research_metrics?: {
    multi_hop_success_rate: number;
    five_plus_table_success_rate: number;
    clarification_rate: number;
    fallback_rate: number;
  };
};

export type AuthUser = {
  id: number;
  name: string;
  email: string;
  role: "user" | "admin";
  created_at: string;
  updated_at: string;
  last_login?: string | null;
  is_active: boolean;
};

export type AuthResponse = {
  user: AuthUser;
  csrf_token?: string;
  expires_at?: string;
};

export type PasswordResetDelivery = {
  sent?: boolean;
  status?: string;
  provider?: string;
  reason?: string;
  outbox_path?: string;
};

export type ForgotPasswordResponse = {
  message: string;
  reset_token?: string;
  reset_url?: string;
  email_delivery?: PasswordResetDelivery;
};

export type FeedbackItem = {
  id: number;
  category: string;
  message: string;
  status: string;
  created_at: string;
  user_id?: number;
  user_name?: string;
  user_email?: string;
};

export type HealthResponse = {
  status: string;
  service?: string;
  endpoints?: string[];
  provider?: LlmProviderStatus;
  schema_tables?: string[];
  columns?: number;
};

export type RuntimeProviderConfig = {
  selected: string;
  adapter: string;
  remote_enabled: boolean;
  api_key_present: boolean;
  embeddings_enabled: boolean;
  chat_model: string;
  embedding_model: string;
  local_model: string;
  supported: string[];
  status: LlmProviderStatus;
  timeout_seconds: number;
  max_retries: number;
  temperature: number;
  top_p: number;
  max_tokens: number;
  max_generation_retries: number;
  runtime_configured: boolean;
  runtime_config_path: string;
  runtime_config_provider?: string;
};

export type RuntimeEmailConfig = {
  backend: string;
  smtp_configured: boolean;
  host: string;
  port: number;
  username_present: boolean;
  password_present: boolean;
  sender: string;
  use_tls: boolean;
  use_ssl: boolean;
  timeout_seconds: number;
  outbox_dir: string;
  frontend_origin: string;
  runtime_configured: boolean;
  runtime_config_path: string;
  runtime_config_backend?: string;
};

export type RuntimeConfigResponse = {
  provider: RuntimeProviderConfig;
  email: RuntimeEmailConfig;
  paths: Record<string, string>;
};

export type ConfigureProviderPayload = {
  provider: string;
  model: string;
  base_url: string;
  api_key?: string;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  max_retries?: number;
  timeout_seconds?: number;
  verify?: boolean;
};

export type ConfigureProviderResponse = {
  provider: RuntimeProviderConfig;
  status: LlmProviderStatus;
};

export type ConfigureEmailPayload = {
  backend: string;
  host: string;
  port: number;
  username?: string;
  password?: string;
  sender: string;
  use_tls: boolean;
  use_ssl: boolean;
  timeout_seconds: number;
  outbox_dir?: string;
  frontend_origin: string;
  verify?: boolean;
  test_recipient?: string;
};

export type ConfigureEmailResponse = {
  email: RuntimeEmailConfig;
  delivery?: PasswordResetDelivery | null;
};

export type SchemaCatalogColumn = {
  name: string;
  data_type: string;
  description?: string;
  is_pk?: boolean;
  is_fk?: boolean;
  is_virtual?: boolean;
};

export type SchemaCatalogTable = {
  name: string;
  domain: string;
  purpose: string;
  row_count: string | number;
  columns: SchemaCatalogColumn[];
  relationships: SchemaRelationship[];
  indexes: string[];
  owner?: string;
  tags?: string[];
  version?: string;
  source?: string;
  business_glossary?: Record<string, string>;
  aliases?: string[];
  last_updated: string;
};

export type SchemaCatalogResponse = {
  summary: {
    tables_count: number;
    relationships_count: number;
    dynamic_tables?: number;
    enterprise_virtual_tables: number;
    enterprise_virtual_relationships: number;
  };
  tables: SchemaCatalogTable[];
  relationships: Record<string, SchemaRelationship[]>;
  enterprise_preview: {
    tables_count: number;
    relationships_count: number;
    domains_count: number;
    supported_scales: string[];
  };
};

export type EnterpriseSchemaResponse = {
  summary: {
    tables_count: number;
    relationships_count: number;
    domains_count: number;
    supported_scales: string[];
  };
  domains: string[];
  tables: Array<{
    name: string;
    domain: string;
    purpose: string;
    row_count: number;
    columns: SchemaCatalogColumn[];
    indexes: string[];
    last_updated: string;
  }>;
  relationships: Array<SchemaRelationship & { relationship_type: string }>;
};

export type SchemaRequest = {
  request_id: number;
  timestamp: string;
  user_notes: string;
  requested_tables: string | string[];
  requested_columns: string[];
  business_context: string;
  status: "pending" | "approved" | "generated" | "rejected";
  generated_schema: Record<string, unknown>;
  requested_by_user_id?: number;
  request_kind?: string;
  attachment_name?: string;
  has_attachment?: boolean;
};

export type SchemaRequestsResponse = {
  requests: SchemaRequest[];
  analytics: {
    total_requests: number;
    status_counts: Record<string, number>;
    most_requested_domains: Array<[string, number]>;
    pending_requests: number;
  };
};

export type MetadataStatusResponse = {
  status: {
    version: number;
    last_refreshed_at: string;
    reason: string;
    bm25_enabled: boolean;
    faiss_enabled: boolean;
    tables_count: number;
    columns_count: number;
    dynamic_tables_count?: number;
  };
  dynamic_schema_file: string;
  dynamic_tables: SchemaCatalogTable[];
  storage: {
    runtime_root: string;
    faiss_root: string;
    model_root: string;
  };
};

export type SchemaStudioTablePayload = {
  name: string;
  domain?: string;
  purpose?: string;
  owner?: string;
  tags?: string[];
  aliases?: string[];
  version?: string;
  columns: Array<{
    name: string;
    data_type: string;
    description?: string;
    is_pk?: boolean;
    is_fk?: boolean;
    references_table?: string;
    references_column?: string;
  }>;
  relationships?: Array<{
    from_table?: string;
    from_column: string;
    to_table: string;
    to_column: string;
  }>;
  indexes?: string[];
  business_glossary?: Record<string, string>;
};

export type SchemaStudioResponse = {
  table?: SchemaCatalogTable;
  deleted?: string;
  request_id?: number;
  applied_tables?: SchemaCatalogTable[];
  metadata_status: MetadataStatusResponse["status"];
};
