"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { BotIcon, CheckIcon, Loader2Icon, PencilIcon, Plus, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  ApiError,
  createAgent,
  deactivateAgent,
  listAgents,
  listKnowledgeBases,
  updateAgent,
} from "@/lib/api";
import type { Agent, AgentProvider, KnowledgeBase } from "@/lib/types";
import { cn } from "@/lib/utils";
import { resolveOrgId } from "@/lib/org";

interface AgentFormState {
  name: string;
  provider: AgentProvider;
  base_url: string;
  api_key: string;
  model_name: string;
  system_prompt: string;
  max_iterations: string;
  temperature: string;
  top_p: string;
  enable_knowledge_search: boolean;
  is_active: boolean;
  knowledge_base_ids: string[];
}

const PROVIDER_LABELS: Record<AgentProvider, string> = {
  ollama: "Ollama",
  openai: "OpenAI-compatible",
};

const EMPTY_FORM: AgentFormState = {
  name: "",
  provider: "ollama",
  base_url: "",
  api_key: "",
  model_name: "",
  system_prompt: "",
  max_iterations: "10",
  temperature: "",
  top_p: "",
  enable_knowledge_search: true,
  is_active: true,
  knowledge_base_ids: [],
};

function agentToForm(agent: Agent): AgentFormState {
  return {
    name: agent.name,
    provider: agent.provider,
    base_url: agent.base_url ?? "",
    api_key: "",
    model_name: agent.model_name,
    system_prompt: agent.system_prompt ?? "",
    max_iterations: String(agent.max_iterations),
    temperature: agent.temperature != null ? String(agent.temperature) : "",
    top_p: agent.top_p != null ? String(agent.top_p) : "",
    enable_knowledge_search: agent.enable_knowledge_search,
    is_active: agent.is_active,
    knowledge_base_ids: agent.knowledge_base_ids,
  };
}

function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
}

export default function AgentsPage() {
  const [orgId, setOrgId] = useState<string | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<AgentFormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);

  const [editTarget, setEditTarget] = useState<Agent | null>(null);
  const [editForm, setEditForm] = useState<AgentFormState>(EMPTY_FORM);
  const [editing, setEditing] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Initialize org_id
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const resolved = await resolveOrgId();
        if (!cancelled) {
          if (!resolved) {
            setError(
              "Unable to resolve organization. Backend needs /v2/me endpoint or you need to set org_id manually."
            );
            setLoading(false);
            return;
          }
          setOrgId(resolved);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to initialize organization"
          );
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh() {
    if (!orgId) return;
    setLoading(true);
    try {
      await loadAll(orgId);
    } finally {
      setLoading(false);
    }
  }

  async function loadAll(orgIdParam: string, cancelledRef?: { current: boolean }) {
    const [agentsResult, kbsResult] = await Promise.allSettled([
      listAgents(orgIdParam),
      listKnowledgeBases(orgIdParam),
    ]);
    if (cancelledRef?.current) return;

    if (agentsResult.status === "fulfilled") setAgents(agentsResult.value);
    if (kbsResult.status === "fulfilled") setKnowledgeBases(kbsResult.value);

    for (const [label, result] of [
      ["agents", agentsResult],
      ["knowledge bases", kbsResult],
    ] as const) {
      if (result.status === "rejected") {
        const err = result.reason;
        if (err instanceof ApiError && err.status !== 401) {
          toast.error(`Failed to load ${label}`, { description: err.message });
        }
      }
    }
  }

  useEffect(() => {
    if (!orgId) return;

    const cancelledRef = { current: false };
    (async () => {
      setLoading(true);
      try {
        await loadAll(orgId, cancelledRef);
      } finally {
        if (!cancelledRef.current) setLoading(false);
      }
    })();
    return () => {
      cancelledRef.current = true;
    };
  }, [orgId]);

  const sortedAgents = useMemo(
    () =>
      [...agents].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ),
    [agents]
  );

  const kbNameById = useMemo(
    () => new Map(knowledgeBases.map((k) => [k.id, k.name])),
    [knowledgeBases]
  );

  function parseOptionalFloat(value: string): number | undefined {
    const trimmed = value.trim();
    return trimmed === "" ? undefined : Number(trimmed);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!orgId) return;
    setCreating(true);
    try {
      await createAgent(orgId, {
        name: createForm.name.trim(),
        provider: createForm.provider,
        base_url: createForm.base_url.trim() || undefined,
        api_key: createForm.api_key.trim() || undefined,
        model_name: createForm.model_name.trim(),
        system_prompt: createForm.system_prompt.trim() || undefined,
        max_iterations: createForm.max_iterations.trim()
          ? Number(createForm.max_iterations)
          : undefined,
        temperature: parseOptionalFloat(createForm.temperature),
        top_p: parseOptionalFloat(createForm.top_p),
        enable_knowledge_search: createForm.enable_knowledge_search,
        is_active: createForm.is_active,
        knowledge_base_ids: createForm.knowledge_base_ids,
      });
      toast.success("Agent created");
      setCreateOpen(false);
      setCreateForm(EMPTY_FORM);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 409 ? "An agent with that name already exists" : "Failed to create agent",
          { description: err.message }
        );
      }
    } finally {
      setCreating(false);
    }
  }

  function openEdit(agent: Agent) {
    setEditTarget(agent);
    setEditForm(agentToForm(agent));
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editTarget || !orgId) return;
    setEditing(true);
    try {
      await updateAgent(orgId, editTarget.id, {
        name: editForm.name.trim(),
        provider: editForm.provider,
        base_url: editForm.base_url.trim() || undefined,
        api_key: editForm.api_key.trim() || undefined,
        model_name: editForm.model_name.trim(),
        system_prompt: editForm.system_prompt.trim() || undefined,
        max_iterations: editForm.max_iterations.trim() ? Number(editForm.max_iterations) : undefined,
        temperature: parseOptionalFloat(editForm.temperature),
        top_p: parseOptionalFloat(editForm.top_p),
        enable_knowledge_search: editForm.enable_knowledge_search,
        is_active: editForm.is_active,
        knowledge_base_ids: editForm.knowledge_base_ids,
      });
      toast.success("Agent updated");
      setEditTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 409 ? "An agent with that name already exists" : "Failed to update agent",
          { description: err.message }
        );
      }
    } finally {
      setEditing(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget || !orgId) return;
    setDeleting(true);
    try {
      await deactivateAgent(orgId, deleteTarget.id);
      toast.success("Agent deactivated");
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to deactivate agent", { description: err.message });
      }
    } finally {
      setDeleting(false);
    }
  }

  function renderFormFields(
    form: AgentFormState,
    setForm: (updater: (f: AgentFormState) => AgentFormState) => void,
    idPrefix: string,
    isEdit: boolean
  ) {
    return (
      <>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-name`}>Name</Label>
          <Input
            id={`${idPrefix}-name`}
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
            autoFocus
          />
        </div>

        <div className="flex flex-col gap-2 rounded-lg border p-3">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-sm font-medium">Serves these knowledge bases</Label>
            {form.knowledge_base_ids.length > 0 ? (
              <span className="text-xs text-muted-foreground">
                {form.knowledge_base_ids.length} selected
              </span>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">
            Choose which knowledge base(s) this agent should answer for.
          </p>
          {knowledgeBases.length === 0 ? (
            <p className="text-xs text-muted-foreground">No knowledge bases yet.</p>
          ) : (
            <div className="flex max-h-48 flex-wrap gap-1.5 overflow-y-auto pt-1">
              {knowledgeBases.map((kb) => {
                const selected = form.knowledge_base_ids.includes(kb.id);
                return (
                  <button
                    key={kb.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        knowledge_base_ids: toggleId(f.knowledge_base_ids, kb.id),
                      }))
                    }
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                      selected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-input bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    {selected ? <CheckIcon className="size-3" /> : null}
                    {kb.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-provider`}>Provider</Label>
            <Select
              value={form.provider}
              onValueChange={(value) =>
                setForm((f) => ({ ...f, provider: value as AgentProvider }))
              }
            >
              <SelectTrigger id={`${idPrefix}-provider`} className="w-full">
                <SelectValue placeholder="Provider">
                {(value) => PROVIDER_LABELS[value as AgentProvider] ?? ""}
              </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ollama">{PROVIDER_LABELS.ollama}</SelectItem>
                <SelectItem value="openai">{PROVIDER_LABELS.openai}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-model`}>Model</Label>
            <Input
              id={`${idPrefix}-model`}
              placeholder="qwen2.5"
              value={form.model_name}
              onChange={(e) => setForm((f) => ({ ...f, model_name: e.target.value }))}
              required
            />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-base-url`}>Base URL (optional)</Label>
          <Input
            id={`${idPrefix}-base-url`}
            placeholder="defaults to the deployment's provider URL"
            value={form.base_url}
            onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-api-key`}>API key {isEdit ? "(leave blank to keep current)" : "(optional)"}</Label>
          <Input
            id={`${idPrefix}-api-key`}
            type="password"
            value={form.api_key}
            onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
          />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-max-iter`}>Max iterations</Label>
            <Input
              id={`${idPrefix}-max-iter`}
              type="number"
              min={1}
              value={form.max_iterations}
              onChange={(e) => setForm((f) => ({ ...f, max_iterations: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-temperature`}>Temperature</Label>
            <Input
              id={`${idPrefix}-temperature`}
              type="number"
              step="0.1"
              placeholder="default"
              value={form.temperature}
              onChange={(e) => setForm((f) => ({ ...f, temperature: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-top-p`}>Top P</Label>
            <Input
              id={`${idPrefix}-top-p`}
              type="number"
              step="0.05"
              placeholder="default"
              value={form.top_p}
              onChange={(e) => setForm((f) => ({ ...f, top_p: e.target.value }))}
            />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-prompt`}>System prompt (optional)</Label>
          <Textarea
            id={`${idPrefix}-prompt`}
            rows={6}
            placeholder="Write custom instructions for this agent..."
            value={form.system_prompt}
            onChange={(e) => setForm((f) => ({ ...f, system_prompt: e.target.value }))}
          />
          <p className="text-xs text-muted-foreground">
            Leave blank to use the assistant&apos;s default behavior.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.enable_knowledge_search}
            onChange={(e) =>
              setForm((f) => ({ ...f, enable_knowledge_search: e.target.checked }))
            }
          />
          Enable knowledge search tool
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
          />
          Active
        </label>
      </>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="font-heading text-3xl tracking-tight">Agents</h1>
        </div>
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl tracking-tight">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Configure providers, models, and tools, then assign agents to knowledge bases.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} disabled={loading || !orgId}>
          <Plus />
          New agent
        </Button>
      </div>

      <Sheet open={createOpen} onOpenChange={setCreateOpen}>
        <SheetContent className="sm:max-w-lg">
          <SheetHeader className="pr-8">
            <SheetTitle>New agent</SheetTitle>
            <SheetDescription>
              Pick a provider and model, choose which tools it can use, and assign it to knowledge bases.
            </SheetDescription>
          </SheetHeader>
          <form onSubmit={handleCreate} className="flex flex-1 flex-col gap-4 overflow-hidden">
            <div className="flex flex-1 flex-col gap-4 overflow-y-auto pr-1">
              {renderFormFields(createForm, setCreateForm, "create", false)}
            </div>
            <SheetFooter>
              <Button type="submit" disabled={creating}>
                {creating ? <Loader2Icon className="animate-spin" /> : null}
                Create agent
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Provider / Model</TableHead>
              <TableHead>Knowledge Bases</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  Loading agents...
                </TableCell>
              </TableRow>
            ) : sortedAgents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-14 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <BotIcon className="size-6 opacity-50" />
                    <p className="text-sm">No agents yet. Create one to get started.</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              sortedAgents.map((agent) => (
                <TableRow
                  key={agent.id}
                  className="border-l-2 border-l-transparent transition-colors hover:border-l-primary hover:bg-accent/30"
                >
                  <TableCell className="font-medium">{agent.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    <span className="font-mono text-xs">{agent.provider}</span> / {agent.model_name}
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground">
                    {agent.knowledge_base_ids.length === 0
                      ? "—"
                      : agent.knowledge_base_ids
                          .map((id) => kbNameById.get(id) ?? id)
                          .join(", ")}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={agent.is_active ? "default" : "secondary"}
                      className={cn(!agent.is_active && "opacity-70")}
                    >
                      {agent.is_active ? "active" : "inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Edit"
                        onClick={() => openEdit(agent)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Deactivate"
                        onClick={() => setDeleteTarget(agent)}
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Sheet open={!!editTarget} onOpenChange={(open) => !open && setEditTarget(null)}>
        <SheetContent className="sm:max-w-lg">
          <SheetHeader className="pr-8">
            <SheetTitle>Edit agent</SheetTitle>
            <SheetDescription>Update the agent&apos;s configuration.</SheetDescription>
          </SheetHeader>
          <form onSubmit={handleEdit} className="flex flex-1 flex-col gap-4 overflow-hidden">
            <div className="flex flex-1 flex-col gap-4 overflow-y-auto pr-1">
              {renderFormFields(editForm, setEditForm, "edit", true)}
            </div>
            <SheetFooter>
              <Button type="submit" disabled={editing}>
                {editing ? <Loader2Icon className="animate-spin" /> : null}
                Save changes
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Deactivate agent?</AlertDialogTitle>
            <AlertDialogDescription>
              This will deactivate &quot;{deleteTarget?.name}&quot; — it will stop responding to
              new chat requests, but its history stays intact and it can be reactivated later by
              editing it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/80"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? <Loader2Icon className="animate-spin" /> : null}
              Deactivate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
