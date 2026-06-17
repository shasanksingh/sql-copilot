export type CopilotInsights = {
  confidence: number;
  threshold: number;
  valid: boolean;
  validation: string;
  source: string;
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
  coverage_report?: Record<string, unknown>;
  agent_telemetry?: Record<string, unknown>;
  execution_trace?: Record<string, unknown>;
  runtime_metrics?: Record<string, unknown>;
  benchmark_record?: Record<string, unknown>;
  cache_hit?: boolean;
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
  agent_telemetry?: {
    intent_accuracy: number;
    planner_accuracy: number;
    validation_accuracy: number;
    optimization_accuracy: number;
    coverage_score: number;
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
};

export type SchemaCatalogColumn = {
  name: string;
  data_type: string;
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
  last_updated: string;
};

export type SchemaCatalogResponse = {
  summary: {
    tables_count: number;
    relationships_count: number;
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
