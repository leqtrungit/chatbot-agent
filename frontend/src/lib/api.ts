import { clearAuthToken, getAuthHeader } from "@/lib/auth";
import type {
  Agent,
  ApiKey,
  CreateAgentInput,
  CreateApiKeyInput,
  CreateApiKeyResponse,
  CreateDomainInput,
  CreateMcpServerInput,
  Document,
  Domain,
  Job,
  McpServer,
  SendChatMessageInput,
  SendChatMessageResponse,
  UpdateAgentInput,
  UpdateDomainInput,
  UpdateMcpServerInput,
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

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    clearAuthToken();
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
    const authHeader = getAuthHeader();
    if (authHeader) {
      finalHeaders["Authorization"] = authHeader;
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

// ---- Domains ----

export function listDomains(): Promise<Domain[]> {
  return request<Domain[]>("/api/domains");
}

export function createDomain(input: CreateDomainInput): Promise<Domain> {
  return request<Domain>("/api/domains", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateDomain(
  id: string,
  input: UpdateDomainInput
): Promise<Domain> {
  return request<Domain>(`/api/domains/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteDomain(id: string): Promise<void> {
  return request<void>(`/api/domains/${id}`, { method: "DELETE" });
}

export function getDomain(id: string): Promise<Domain> {
  return request<Domain>(`/api/domains/${id}`);
}

export function setDomainAgents(id: string, agentIds: string[]): Promise<Domain> {
  return request<Domain>(`/api/domains/${id}/agents`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_ids: agentIds }),
  });
}

// ---- Agents ----

export function listAgents(): Promise<Agent[]> {
  return request<Agent[]>("/api/agents");
}

export function getAgent(id: string): Promise<Agent> {
  return request<Agent>(`/api/agents/${id}`);
}

export function createAgent(input: CreateAgentInput): Promise<Agent> {
  return request<Agent>("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateAgent(id: string, input: UpdateAgentInput): Promise<Agent> {
  return request<Agent>(`/api/agents/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteAgent(id: string): Promise<void> {
  return request<void>(`/api/agents/${id}`, { method: "DELETE" });
}

// ---- MCP servers ----

export function listMcpServers(): Promise<McpServer[]> {
  return request<McpServer[]>("/api/mcp-servers");
}

export function createMcpServer(input: CreateMcpServerInput): Promise<McpServer> {
  return request<McpServer>("/api/mcp-servers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updateMcpServer(id: string, input: UpdateMcpServerInput): Promise<McpServer> {
  return request<McpServer>(`/api/mcp-servers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteMcpServer(id: string): Promise<void> {
  return request<void>(`/api/mcp-servers/${id}`, { method: "DELETE" });
}

// ---- Documents ----

export function listDocuments(domainId: string): Promise<Document[]> {
  return request<Document[]>(`/api/domains/${domainId}/documents`);
}

export function uploadDocument(
  domainId: string,
  file: File
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  return request<Document>(`/api/domains/${domainId}/documents`, {
    method: "POST",
    body: formData,
  });
}

export function getDocument(id: string): Promise<Document> {
  return request<Document>(`/api/documents/${id}`);
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${id}`, { method: "DELETE" });
}

// ---- API keys ----

export function listApiKeys(): Promise<ApiKey[]> {
  return request<ApiKey[]>("/api/api-keys");
}

export function createApiKey(
  input: CreateApiKeyInput
): Promise<CreateApiKeyResponse> {
  return request<CreateApiKeyResponse>("/api/api-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function revokeApiKey(id: string): Promise<ApiKey> {
  return request<ApiKey>(`/api/api-keys/${id}/revoke`, { method: "POST" });
}

// ---- Webhook / Jobs (no admin auth — authenticated via X-API-Key) ----

export function sendChatMessage(
  input: SendChatMessageInput,
  apiKey: string
): Promise<SendChatMessageResponse> {
  return request<SendChatMessageResponse>("/api/webhooks/generic", {
    auth: false,
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(input),
  });
}

export function getJob(jobId: string, apiKey: string): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}`, {
    auth: false,
    headers: { "X-API-Key": apiKey },
  });
}

export async function streamChatMessage(
  input: SendChatMessageInput,
  apiKey: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(input),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError(0, "Request cancelled");
    }
    throw new ApiError(0, "Network error: could not reach the server");
  }

  if (!response.ok || !response.body) {
    const detail = await parseErrorDetail(response);
    throw new ApiError(response.status, detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        const line = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;

        try {
          onEvent(JSON.parse(line.slice(5).trim()) as ChatStreamEvent);
        } catch (err) {
          console.error("Failed to parse SSE frame:", err);
        }
      }
    }
  } finally {
    reader.cancel();
  }
}

export { API_BASE_URL };
