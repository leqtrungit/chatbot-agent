"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Loader2Icon, PencilIcon, Plus, PlugZap, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  updateMcpServer,
} from "@/lib/api";
import type { McpServer, McpTransport } from "@/lib/types";

interface McpFormState {
  name: string;
  url: string;
  transport: McpTransport;
  headerName: string;
  headerValue: string;
  is_active: boolean;
}

const TRANSPORT_LABELS: Record<McpTransport, string> = {
  http: "HTTP (streamable)",
  sse: "SSE",
};

const EMPTY_FORM: McpFormState = {
  name: "",
  url: "",
  transport: "http",
  headerName: "",
  headerValue: "",
  is_active: true,
};

function formToHeaders(form: McpFormState): Record<string, string> | undefined {
  if (!form.headerName.trim()) return undefined;
  return { [form.headerName.trim()]: form.headerValue };
}

function serverToForm(server: McpServer): McpFormState {
  const [headerName, headerValue] = Object.entries(server.headers ?? {})[0] ?? ["", ""];
  return {
    name: server.name,
    url: server.url,
    transport: server.transport,
    headerName,
    headerValue,
    is_active: server.is_active,
  };
}

export default function McpServersPage() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<McpFormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);

  const [editTarget, setEditTarget] = useState<McpServer | null>(null);
  const [editForm, setEditForm] = useState<McpFormState>(EMPTY_FORM);
  const [editing, setEditing] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<McpServer | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      setServers(await listMcpServers());
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401) {
        toast.error("Failed to load MCP servers", { description: err.message });
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await listMcpServers();
        if (!cancelled) setServers(data);
      } catch (err) {
        if (!cancelled && err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load MCP servers", { description: err.message });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedServers = useMemo(
    () =>
      [...servers].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ),
    [servers]
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    try {
      await createMcpServer({
        name: createForm.name.trim(),
        url: createForm.url.trim(),
        transport: createForm.transport,
        headers: formToHeaders(createForm),
        is_active: createForm.is_active,
      });
      toast.success("MCP server created");
      setCreateOpen(false);
      setCreateForm(EMPTY_FORM);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 409 ? "An MCP server with that name already exists" : "Failed to create MCP server",
          { description: err.message }
        );
      }
    } finally {
      setCreating(false);
    }
  }

  function openEdit(server: McpServer) {
    setEditTarget(server);
    setEditForm(serverToForm(server));
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editTarget) return;
    setEditing(true);
    try {
      await updateMcpServer(editTarget.id, {
        name: editForm.name.trim(),
        url: editForm.url.trim(),
        transport: editForm.transport,
        headers: formToHeaders(editForm) ?? {},
        is_active: editForm.is_active,
      });
      toast.success("MCP server updated");
      setEditTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 409 ? "An MCP server with that name already exists" : "Failed to update MCP server",
          { description: err.message }
        );
      }
    } finally {
      setEditing(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteMcpServer(deleteTarget.id);
      toast.success("MCP server deleted");
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to delete MCP server", { description: err.message });
      }
    } finally {
      setDeleting(false);
    }
  }

  function renderFormFields(
    form: McpFormState,
    setForm: (updater: (f: McpFormState) => McpFormState) => void,
    idPrefix: string
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
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-url`}>URL</Label>
          <Input
            id={`${idPrefix}-url`}
            placeholder="https://example.com/mcp"
            value={form.url}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            required
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-transport`}>Transport</Label>
          <Select
            value={form.transport}
            onValueChange={(value) => setForm((f) => ({ ...f, transport: value as McpTransport }))}
          >
            <SelectTrigger id={`${idPrefix}-transport`} className="w-full">
              <SelectValue placeholder="Transport">
                {(value) => TRANSPORT_LABELS[value as McpTransport] ?? ""}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="http">{TRANSPORT_LABELS.http}</SelectItem>
              <SelectItem value="sse">{TRANSPORT_LABELS.sse}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-header-name`}>Auth header (optional)</Label>
            <Input
              id={`${idPrefix}-header-name`}
              placeholder="Authorization"
              value={form.headerName}
              onChange={(e) => setForm((f) => ({ ...f, headerName: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-header-value`}>Header value</Label>
            <Input
              id={`${idPrefix}-header-value`}
              type="password"
              placeholder="Bearer ..."
              value={form.headerValue}
              onChange={(e) => setForm((f) => ({ ...f, headerValue: e.target.value }))}
            />
          </div>
        </div>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl tracking-tight">MCP Servers</h1>
          <p className="text-sm text-muted-foreground">
            Register remote MCP (Model Context Protocol) servers agents can use as tools.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus />New server
        </Button>
        <Sheet open={createOpen} onOpenChange={setCreateOpen}>
          <SheetContent>
            <SheetHeader className="pr-8">
              <SheetTitle>New MCP server</SheetTitle>
              <SheetDescription>
                Register a remote HTTP/SSE MCP server. Its tools become available to any agent it is attached to.
              </SheetDescription>
            </SheetHeader>
            <form onSubmit={handleCreate} className="flex flex-1 flex-col gap-4 overflow-y-auto">
              {renderFormFields(createForm, setCreateForm, "create")}
              <SheetFooter>
                <Button type="submit" disabled={creating}>
                  {creating ? <Loader2Icon className="animate-spin" /> : null}
                  Create server
                </Button>
              </SheetFooter>
            </form>
          </SheetContent>
        </Sheet>
      </div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>URL</TableHead>
              <TableHead>Transport</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  Loading MCP servers...
                </TableCell>
              </TableRow>
            ) : sortedServers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-14 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <PlugZap className="size-6 opacity-50" />
                    <p className="text-sm">No MCP servers yet. Register one to get started.</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              sortedServers.map((server) => (
                <TableRow
                  key={server.id}
                  className="border-l-2 border-l-transparent transition-colors hover:border-l-primary hover:bg-accent/30"
                >
                  <TableCell className="font-medium">{server.name}</TableCell>
                  <TableCell className="max-w-xs truncate font-mono text-xs text-muted-foreground">
                    {server.url}
                  </TableCell>
                  <TableCell className="text-muted-foreground uppercase">{server.transport}</TableCell>
                  <TableCell>
                    <Badge variant={server.is_active ? "default" : "secondary"}>
                      {server.is_active ? "active" : "inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Edit"
                        onClick={() => openEdit(server)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Delete"
                        onClick={() => setDeleteTarget(server)}
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
        <SheetContent>
          <SheetHeader className="pr-8">
            <SheetTitle>Edit MCP server</SheetTitle>
            <SheetDescription>Update the server&apos;s connection details.</SheetDescription>
          </SheetHeader>
          <form onSubmit={handleEdit} className="flex flex-1 flex-col gap-4 overflow-y-auto">
            {renderFormFields(editForm, setEditForm, "edit")}
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
            <AlertDialogTitle>Delete MCP server?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{deleteTarget?.name}&quot; and detach it from any
              agents using it. This action cannot be undone.
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
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
