export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface Domain {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
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
  domain_id: string;
  session_id?: string;
  message: string;
  metadata?: Record<string, unknown>;
}

export interface SendChatMessageResponse {
  job_id: string;
}

export type JobStatus = "queued" | "in_progress" | "complete" | "failed" | "not_found";

export interface JobResult {
  reply: string;
  session_id: string;
  iterations: number;
  stopped_on: string;
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
