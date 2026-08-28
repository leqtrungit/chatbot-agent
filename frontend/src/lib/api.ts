import { clearAllTokens, getAccessToken } from "@/lib/auth";
import type {
  Agent,
  ApiKey,
  CreateAgentInput,
  CreateApiKeyInput,
  CreateApiKeyResponse,
  CreateKnowledgeBaseInput,
  Document,
  UpdateAgentInput,
  UpdateKnowledgeBaseInput,
  KnowledgeBase,
} from "@/lib/types";

export interface ChatStreamEvent {
  type: "queued" | "thinking" | "token" | "done" | "error";
  job_id?: string;
  delta?: string;
  reply?: string;
  session_id?: string;
  iterations?: number;
  stopped_on?: string;
  message?: string;
}

// API base URL: empty by default (uses proxy), or explicit cross-origin
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  status: number;
  detail?: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function redirectToLogin() {
  if (typeof window !== "undefined") {
    clearAllTokens();
    window.location.href = "/login";
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const data = await response.clone().json();
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail) return JSON.stringify(data.detail);
    return response.statusText;
  } catch {
    return response.statusText;
  }
}

interface RequestOptions {
  auth?: boolean;
  method?: string;
  body?: BodyInit;
  headers?: Record<string, string>;
}

async function request<T>(
  path: string,
  { auth = true, method = "GET", body, headers = {} }: RequestOptions = {}
): Promise<T> {
  const finalHeaders: Record<string, string> = { ...headers };

  if (auth) {
    const token = await getAccessToken();
    if (token) {
      finalHeaders["Authorization"] = `Bearer ${token}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      body,
      headers: finalHeaders,
    });
  } catch {
    throw new ApiError(0, "Network error: could not reach the server");
  }

  if (response.status === 401 && auth) {
    redirectToLogin();
    throw new ApiError(401, "Unauthorized");
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  return undefined as T;
}

// ---- Knowledge Bases (formerly Domains) ----

export function listKnowledgeBases(orgId: string): Promise<KnowledgeBase[]> {
  return request<KnowledgeBase[]>(`/v2/orgs/${orgId}/knowledge-bases`);
}

export function createKnowledgeBase(
  orgId: string,
  input: CreateKnowledgeBaseInput
): Promise<KnowledgeBase> {
  return request<KnowledgeBase>(`/v2/orgs/${orgId}/knowledge-bases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateKnowledgeBase(
  orgId: string,
  kbId: string,
  input: UpdateKnowledgeBaseInput
): Promise<KnowledgeBase> {
  return request<KnowledgeBase>(`/v2/orgs/${orgId}/knowledge-bases/${kbId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteKnowledgeBase(orgId: string, kbId: string): Promise<void> {
  return request<void>(`/v2/orgs/${orgId}/knowledge-bases/${kbId}`, {
    method: "DELETE",
  });
}

export function getKnowledgeBase(orgId: string, kbId: string): Promise<KnowledgeBase> {
  return request<KnowledgeBase>(`/v2/orgs/${orgId}/knowledge-bases/${kbId}`);
}

// ---- Agents ----

export function listAgents(orgId: string): Promise<Agent[]> {
  return request<Agent[]>(`/v2/orgs/${orgId}/agents`);
}

export function getAgent(orgId: string, agentId: string): Promise<Agent> {
  return request<Agent>(`/v2/orgs/${orgId}/agents/${agentId}`);
}

export function createAgent(
  orgId: string,
  input: CreateAgentInput
): Promise<Agent> {
  return request<Agent>(`/v2/orgs/${orgId}/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateAgent(
  orgId: string,
  agentId: string,
  input: UpdateAgentInput
): Promise<Agent> {
  return request<Agent>(`/v2/orgs/${orgId}/agents/${agentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deactivateAgent(orgId: string, agentId: string): Promise<void> {
  return request<void>(`/v2/orgs/${orgId}/agents/${agentId}/deactivate`, {
    method: "POST",
  });
}

// ---- Documents ----

export function listDocuments(orgId: string, kbId: string): Promise<Document[]> {
  return request<Document[]>(`/v2/orgs/${orgId}/knowledge-bases/${kbId}/documents`);
}

export function uploadDocument(
  orgId: string,
  kbId: string,
  file: File
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  return request<Document>(`/v2/orgs/${orgId}/knowledge-bases/${kbId}/documents`, {
    method: "POST",
    body: formData,
  });
}

export function getDocument(
  orgId: string,
  kbId: string,
  docId: string
): Promise<Document> {
  return request<Document>(
    `/v2/orgs/${orgId}/knowledge-bases/${kbId}/documents/${docId}`
  );
}

export function deleteDocument(
  orgId: string,
  kbId: string,
  docId: string
): Promise<void> {
  return request<void>(
    `/v2/orgs/${orgId}/knowledge-bases/${kbId}/documents/${docId}`,
    { method: "DELETE" }
  );
}

// ---- API Keys ----

export function listApiKeys(orgId: string): Promise<ApiKey[]> {
  return request<ApiKey[]>(`/v2/orgs/${orgId}/api-keys`);
}

export function createApiKey(
  orgId: string,
  input: CreateApiKeyInput
): Promise<CreateApiKeyResponse> {
  return request<CreateApiKeyResponse>(`/v2/orgs/${orgId}/api-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function revokeApiKey(orgId: string, keyId: string): Promise<ApiKey> {
  return request<ApiKey>(`/v2/orgs/${orgId}/api-keys/${keyId}/revoke`, {
    method: "POST",
  });
}

export { API_BASE_URL };
