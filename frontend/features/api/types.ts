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
};

export type MetricsResponse = {
  total: number;
  average_reward: number;
  query_success_rate: number;
  sql_accuracy: number;
  average_latency: number;
  trend: FeedbackTrendPoint[];
};

export type HealthResponse = {
  status: string;
  service?: string;
  endpoints?: string[];
};
