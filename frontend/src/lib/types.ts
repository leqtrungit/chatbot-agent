export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface Domain {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  agent_ids: string[];
}

export interface CreateDomainInput {
  name: string;
  slug?: string;
  description?: string;
}

export interface UpdateDomainInput {
  name?: string;
  slug?: string;
  description?: string;
}

export interface Document {
  id: string;
  domain_id: string;
  filename: string;
  mime_type: string;
  status: DocumentStatus;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SendChatMessageInput {
  agent_id: string;
  session_id?: string;
  message: string;
  metadata?: Record<string, unknown>;
}

export type AgentProvider = "ollama" | "openai";

export interface Agent {
  id: string;
  name: string;
  provider: AgentProvider;
  base_url?: string | null;
  model_name: string;
  system_prompt?: string | null;
  max_iterations: number;
  temperature?: number | null;
  top_p?: number | null;
  enable_knowledge_search: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  mcp_server_ids: string[];
  domain_ids: string[];
}

export interface CreateAgentInput {
  name: string;
  provider: AgentProvider;
  base_url?: string;
  api_key?: string;
  model_name: string;
  system_prompt?: string | null;
  max_iterations?: number;
  temperature?: number;
  top_p?: number;
  enable_knowledge_search?: boolean;
  is_active?: boolean;
  mcp_server_ids?: string[];
  domain_ids?: string[];
}

export interface UpdateAgentInput {
  name?: string;
  provider?: AgentProvider;
  base_url?: string;
  api_key?: string;
  model_name?: string;
  system_prompt?: string | null;
  max_iterations?: number;
  temperature?: number;
  top_p?: number;
  enable_knowledge_search?: boolean;
  is_active?: boolean;
  mcp_server_ids?: string[];
  domain_ids?: string[];
}

export type McpTransport = "http" | "sse";

export interface McpServer {
  id: string;
  name: string;
  url: string;
  transport: McpTransport;
  headers?: Record<string, string> | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateMcpServerInput {
  name: string;
  url: string;
  transport?: McpTransport;
  headers?: Record<string, string>;
  is_active?: boolean;
}

export interface UpdateMcpServerInput {
  name?: string;
  url?: string;
  transport?: McpTransport;
  headers?: Record<string, string>;
  is_active?: boolean;
}

export interface SendChatMessageResponse {
  job_id: string;
}

export type JobStatus = "queued" | "in_progress" | "complete" | "failed" | "not_found";

export interface Citation {
  marker: number;
  source_id: string;
  title: string;
  snippet: string;
  score: number | null;
  metadata: Record<string, unknown>;
}

export interface JobResult {
  reply: string;
  session_id: string;
  iterations: number;
  stopped_on: string;
  citations?: Citation[];
}

export interface Job {
  job_id: string;
  status: JobStatus;
  result: JobResult | null;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  rate_limit_per_minute?: number | null;
  created_at: string;
  revoked_at?: string | null;
}

export interface CreateApiKeyInput {
  name: string;
  rate_limit_per_minute?: number;
}

export interface CreateApiKeyResponse {
  id: string;
  name: string;
  key: string;
}

// ---- Analytics ----

export type AnalyticsRange = "24h" | "7d" | "30d";
export type BreakdownBy = "api_key" | "agent" | "model" | "status";

export interface UsageSummary {
  total_requests: number;
  success_requests: number;
  error_requests: number;
  error_rate: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  avg_latency_ms: number;
}

export interface TimeseriesPoint {
  bucket: string;
  requests: number;
  total_tokens: number;
  error_count: number;
}

export interface BreakdownRow {
  key: string;
  key_id?: string | null;
  requests: number;
  total_tokens: number;
  error_count: number;
}
