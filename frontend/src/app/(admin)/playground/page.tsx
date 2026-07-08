"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Loader2Icon, RotateCcwIcon, SendIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, getJob, listDomains, sendChatMessage } from "@/lib/api";
import type { Domain, JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "error";
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

export default function PlaygroundPage() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainId, setDomainId] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>(newId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [jobStatusText, setJobStatusText] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await listDomains();
        setDomains(data);
        if (data.length > 0) setDomainId(data[0].id);
      } catch (err) {
        if (err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load domains", { description: err.message });
        }
      }
    }
    load();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  function resetConversation() {
    setSessionId(newId());
    setMessages([]);
    setJobStatusText(null);
  }

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
        job = await getJob(jobId);
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
    if (!trimmed || !domainId || sending) return;

    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: trimmed },
    ]);
    setInput("");
    setSending(true);
    setJobStatusText("queued");

    try {
      const { job_id } = await sendChatMessage({
        domain_id: domainId,
        session_id: sessionId,
        message: trimmed,
      });
      await pollJob(job_id);
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

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Playground</h1>
          <p className="text-sm text-muted-foreground">
            Send test messages to a domain and inspect the assistant&apos;s replies.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={domainId || undefined}
            onValueChange={(value) => setDomainId(value as string)}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Select a domain" />
            </SelectTrigger>
            <SelectContent>
              {domains.map((domain) => (
                <SelectItem key={domain.id} value={domain.id}>
                  {domain.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            aria-label="Reset conversation"
            onClick={resetConversation}
          >
            <RotateCcwIcon />
          </Button>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden rounded-xl border">
        <div
          ref={scrollRef}
          className="flex flex-1 flex-col gap-3 overflow-y-auto p-4"
          style={{ minHeight: 400, maxHeight: "60vh" }}
        >
          {messages.length === 0 ? (
            <p className="m-auto text-sm text-muted-foreground">
              {selectedDomain
                ? `No messages yet. Say hello to ${selectedDomain.name}.`
                : "Select a domain to start chatting."}
            </p>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex",
                  msg.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[75%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap",
                    msg.role === "user" &&
                      "bg-primary text-primary-foreground",
                    msg.role === "assistant" && "bg-muted text-foreground",
                    msg.role === "error" &&
                      "bg-destructive/10 text-destructive"
                  )}
                >
                  {msg.content}
                </div>
              </div>
            ))
          )}
          {sending && jobStatusText ? (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground">
                <Loader2Icon className="size-3.5 animate-spin" />
                {jobStatusText}
              </div>
            </div>
          ) : null}
        </div>
        <form
          onSubmit={handleSend}
          className="flex items-center gap-2 border-t bg-muted/30 p-3"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              domainId ? "Type a message..." : "Select a domain first"
            }
            disabled={!domainId || sending}
          />
          <Button type="submit" disabled={!domainId || !input.trim() || sending}>
            {sending ? (
              <Loader2Icon className="animate-spin" />
            ) : (
              <SendIcon />
            )}
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
