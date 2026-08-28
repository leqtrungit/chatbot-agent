export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface KnowledgeBase {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateKnowledgeBaseInput {
  name: string;
  slug?: string;
  description?: string;
}

export interface UpdateKnowledgeBaseInput {
  name?: string;
  slug?: string;
  description?: string;
}

// Keep Domain as an alias for backward compatibility
export type Domain = KnowledgeBase;
export type CreateDomainInput = CreateKnowledgeBaseInput;
export type UpdateDomainInput = UpdateKnowledgeBaseInput;

export interface Document {
  id: string;
  knowledge_base_id: string;
  filename: string;
  mime_type: string;
  status: DocumentStatus;
  error?: string | null;
  created_at: string;
  updated_at: string;
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
  knowledge_base_ids: string[];
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
  knowledge_base_ids?: string[];
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
  knowledge_base_ids?: string[];
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
