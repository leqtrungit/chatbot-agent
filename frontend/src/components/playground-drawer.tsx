"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ChevronDownIcon, Loader2Icon, RotateCcwIcon, SendIcon } from "lucide-react";
import { ThinkingOrb, type OrbState } from "thinking-orbs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ApiError,
  getJob,
  listDomains,
  sendChatMessage, // eslint-disable-line @typescript-eslint/no-unused-vars
  streamChatMessage,
  type ChatStreamEvent,
} from "@/lib/api";
import type { Domain, JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "thinking" | "error";
  content: string;
  jobStatus?: JobStatus;
}

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 2 * 60 * 1000;

function newId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

const API_KEY_STORAGE_KEY = "playground_api_key";

function orbStateForStatus(status: string | null): OrbState {
  switch (status) {
    case "thinking":
      return "shaping";
    case "processing":
      return "working";
    case "queued":
    default:
      return "connecting";
  }
}

function ThinkingBubble({
  content,
  collapsed,
  onToggle,
}: {
  content: string;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const contentRef = useRef<HTMLDivElement>(null);

  // Keep the live ticker pinned to its latest line without animating —
  // an animated/outer-container scroll here is what caused the jitter.
  useEffect(() => {
    if (collapsed) return;
    const el = contentRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [content, collapsed]);

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl border border-primary/25 bg-primary/5 px-3 py-2 text-sm text-muted-foreground">
        <button
          type="button"
          onClick={onToggle}
          className="flex items-center gap-2 font-medium text-foreground"
        >
          <ThinkingOrb state="shaping" size={20} paused={collapsed} />
          Thinking
          <ChevronDownIcon
            className={cn(
              "size-3.5 transition-transform",
              collapsed && "-rotate-90"
            )}
          />
        </button>
        {!collapsed ? (
          <div
            ref={contentRef}
            className="mt-1.5 max-h-24 overflow-y-auto whitespace-pre-wrap italic [mask-image:linear-gradient(to_bottom,transparent,black_16px)]"
          >
            {content}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function PlaygroundDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainId, setDomainId] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>(newId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [jobStatusText, setJobStatusText] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState<string>("");
  const [collapsedThinking, setCollapsedThinking] = useState<
    Record<string, boolean>
  >({});
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(API_KEY_STORAGE_KEY);
    if (stored) setApiKey(stored);
  }, []);

  function handleApiKeyChange(value: string) {
    setApiKey(value);
    window.localStorage.setItem(API_KEY_STORAGE_KEY, value);
  }

  useEffect(() => {
    if (!open) return;
    async function load() {
      try {
        const data = await listDomains();
        setDomains(data);
        setDomainId((current) => current || (data.length > 0 ? data[0].id : ""));
      } catch (err) {
        if (err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load domains", { description: err.message });
        }
      }
    }
    load();
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "auto",
    });
  }, [messages]);

  function resetConversation() {
    setSessionId(newId());
    setMessages([]);
    setJobStatusText(null);
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async function pollJob(jobId: string): Promise<void> {
    const start = Date.now();

    while (true) {
      if (Date.now() - start > POLL_TIMEOUT_MS) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "error",
            content: "Timed out waiting for a response.",
          },
        ]);
        setJobStatusText(null);
        return;
      }

      let job;
      try {
        job = await getJob(jobId, apiKey);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "error",
            content:
              err instanceof ApiError ? err.message : "Failed to fetch job status.",
          },
        ]);
        setJobStatusText(null);
        return;
      }

      setJobStatusText(job.status);

      if (job.status === "complete") {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "assistant",
            content: job.result?.reply ?? "(empty reply)",
          },
        ]);
        setJobStatusText(null);
        return;
      }

      if (job.status === "failed" || job.status === "not_found") {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "error",
            content:
              job.status === "not_found"
                ? "Job not found."
                : "The assistant failed to generate a response.",
          },
        ]);
        setJobStatusText(null);
        return;
      }

      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || !domainId || !apiKey.trim() || sending) return;

    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: trimmed },
    ]);
    setInput("");
    setSending(true);
    setJobStatusText("queued");

    let assistantMessageCreated = false;
    let thinkingMessageId: string | null = null;

    try {
      await streamChatMessage(
        {
          domain_id: domainId,
          session_id: sessionId,
          message: trimmed,
        },
        apiKey,
        (streamEvent: ChatStreamEvent) => {
          if (streamEvent.type === "queued") {
            setJobStatusText("processing");
          } else if (streamEvent.type === "thinking") {
            const delta = streamEvent.delta || "";
            setJobStatusText("thinking");
            if (!thinkingMessageId) {
              const id = newId();
              thinkingMessageId = id;
              setMessages((prev) => [
                ...prev,
                { id, role: "thinking", content: delta },
              ]);
            } else {
              const id = thinkingMessageId;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === id ? { ...m, content: m.content + delta } : m
                )
              );
            }
          } else if (streamEvent.type === "token") {
            if (thinkingMessageId) {
              const id = thinkingMessageId;
              setCollapsedThinking((prev) => ({ ...prev, [id]: true }));
            }
            const delta = streamEvent.delta || "";
            if (!assistantMessageCreated) {
              // Create assistant message on first token
              setMessages((prev) => [
                ...prev,
                {
                  id: newId(),
                  role: "assistant",
                  content: delta,
                },
              ]);
              assistantMessageCreated = true;
            } else {
              // Append delta to existing assistant message
              setMessages((prev) => {
                const updated = [...prev];
                const lastMsg = updated[updated.length - 1];
                if (lastMsg && lastMsg.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...lastMsg,
                    content: lastMsg.content + delta,
                  };
                }
                return updated;
              });
            }
          } else if (streamEvent.type === "done") {
            setJobStatusText(null);
          } else if (streamEvent.type === "error") {
            setMessages((prev) => [
              ...prev,
              {
                id: newId(),
                role: "error",
                content: streamEvent.message || "An error occurred.",
              },
            ]);
            setJobStatusText(null);
          }
        }
      );
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "error",
          content:
            err instanceof ApiError ? err.message : "Failed to send message.",
        },
      ]);
      setJobStatusText(null);
    } finally {
      setSending(false);
    }
  }

  const selectedDomain = domains.find((d) => d.id === domainId);
  const lastMessage = messages[messages.length - 1];
  // Once a thinking bubble or the assistant's own reply has started
  // rendering, that bubble is already the live indicator — showing this
  // pill at the same time doubles up the orb for no reason.
  const showStatusPill =
    sending &&
    jobStatusText &&
    (!lastMessage || lastMessage.role === "user" || lastMessage.role === "error");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-xl">
        <SheetHeader className="pr-8">
          <div className="flex items-center justify-between gap-2">
            <SheetTitle>Playground</SheetTitle>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Reset conversation"
              onClick={resetConversation}
            >
              <RotateCcwIcon />
            </Button>
          </div>
          <SheetDescription>
            Send test messages to a domain and inspect the assistant&apos;s replies.
          </SheetDescription>
          <div className="flex items-center gap-2 pt-1">
            <Input
              className="flex-1"
              type="password"
              placeholder="X-API-Key"
              value={apiKey}
              onChange={(e) => handleApiKeyChange(e.target.value)}
              aria-label="API key"
            />
            <Select
              value={domainId}
              onValueChange={(value) => setDomainId(value as string)}
            >
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Domain">
                  {(value) =>
                    domains.find((domain) => domain.id === value)?.name ?? ""
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {domains.map((domain) => (
                  <SelectItem key={domain.id} value={domain.id}>
                    {domain.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {!apiKey.trim() ? (
            <p className="text-xs text-muted-foreground">
              Enter an API key above (create one on the API Keys page) to send
              messages.
            </p>
          ) : null}
        </SheetHeader>

        <div
          ref={scrollRef}
          className="flex flex-1 flex-col gap-3 overflow-y-auto rounded-xl border p-3"
        >
          {messages.length === 0 ? (
            <p className="m-auto text-sm text-muted-foreground">
              {selectedDomain
                ? `No messages yet. Say hello to ${selectedDomain.name}.`
                : "Select a domain to start chatting."}
            </p>
          ) : (
            messages.map((msg) => {
              if (msg.role === "thinking") {
                const collapsed = collapsedThinking[msg.id] ?? false;
                return (
                  <ThinkingBubble
                    key={msg.id}
                    content={msg.content}
                    collapsed={collapsed}
                    onToggle={() =>
                      setCollapsedThinking((prev) => ({
                        ...prev,
                        [msg.id]: !collapsed,
                      }))
                    }
                  />
                );
              }

              return (
                <div
                  key={msg.id}
                  className={cn(
                    "flex",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap",
                      msg.role === "user" &&
                        "bg-primary text-primary-foreground",
                      msg.role === "assistant" &&
                        "border border-border/70 bg-card text-foreground",
                      msg.role === "error" &&
                        "bg-destructive/10 text-destructive"
                    )}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })
          )}
          {showStatusPill ? (
            <div className="flex justify-start">
              <div className="inline-flex h-9 items-center gap-2 rounded-full border border-border/70 bg-card pl-2 pr-3.5 text-xs text-muted-foreground shadow-sm">
                <ThinkingOrb state={orbStateForStatus(jobStatusText)} size={20} />
                {jobStatusText}
              </div>
            </div>
          ) : null}
        </div>

        <form onSubmit={handleSend} className="flex items-center gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              !apiKey.trim()
                ? "Enter an API key above first"
                : domainId
                  ? "Type a message..."
                  : "Select a domain first"
            }
            disabled={!domainId || !apiKey.trim() || sending}
          />
          <Button
            type="submit"
            disabled={!domainId || !apiKey.trim() || !input.trim() || sending}
          >
            {sending ? <Loader2Icon className="animate-spin" /> : <SendIcon />}
            Send
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
