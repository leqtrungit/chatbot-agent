"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AlertTriangleIcon, CopyIcon, KeyRoundIcon, Loader2Icon, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import { ApiError, createApiKey, listApiKeys, revokeApiKey } from "@/lib/api";
import type { ApiKey } from "@/lib/types";

interface CreateFormState {
  name: string;
  rateLimitPerMinute: string;
}

const EMPTY_FORM: CreateFormState = { name: "", rateLimitPerMinute: "" };

export default function ApiKeysPage() {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [revoking, setRevoking] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listApiKeys();
      setApiKeys(data);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401) {
        toast.error("Failed to load API keys", { description: err.message });
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
        const data = await listApiKeys();
        if (!cancelled) setApiKeys(data);
      } catch (err) {
        if (!cancelled && err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load API keys", { description: err.message });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedKeys = useMemo(
    () =>
      [...apiKeys].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ),
    [apiKeys]
  );

  function closeCreateDialog(open: boolean) {
    setCreateOpen(open);
    if (!open) {
      setCreateForm(EMPTY_FORM);
      setCreatedKey(null);
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    try {
      const rateLimit = createForm.rateLimitPerMinute.trim();
      const response = await createApiKey({
        name: createForm.name.trim(),
        rate_limit_per_minute: rateLimit ? Number(rateLimit) : undefined,
      });
      setCreatedKey(response.key);
      toast.success("API key created");
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to create API key", { description: err.message });
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleCopy(key: string) {
    try {
      await navigator.clipboard.writeText(key);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }

  async function handleRevoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    try {
      await revokeApiKey(revokeTarget.id);
      toast.success("API key revoked");
      setRevokeTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to revoke API key", { description: err.message });
      }
    } finally {
      setRevoking(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API Keys</h1>
          <p className="text-sm text-muted-foreground">
            Manage the integration apps (mobile app, website widget, bot...)
            allowed to call the chat webhook.
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={closeCreateDialog}>
          <DialogTrigger render={<Button><Plus />New API key</Button>} />
          <DialogContent>
            {createdKey ? (
              <>
                <DialogHeader>
                  <DialogTitle>API key created</DialogTitle>
                  <DialogDescription>
                    Copy this key now — it will not be shown again.
                  </DialogDescription>
                </DialogHeader>
                <div className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2 font-mono text-sm">
                  <span className="flex-1 truncate">{createdKey}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Copy key"
                    onClick={() => handleCopy(createdKey)}
                  >
                    <CopyIcon />
                  </Button>
                </div>
                <p className="flex items-start gap-2 text-sm text-muted-foreground">
                  <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-amber-500" />
                  Store this key securely. Anyone with it can call the webhook
                  as this app.
                </p>
                <DialogFooter>
                  <Button type="button" onClick={() => closeCreateDialog(false)}>
                    Done
                  </Button>
                </DialogFooter>
              </>
            ) : (
              <>
                <DialogHeader>
                  <DialogTitle>New API key</DialogTitle>
                  <DialogDescription>
                    Create a key for a new integration app. It is shown once.
                  </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleCreate} className="flex flex-col gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="create-name">App name</Label>
                    <Input
                      id="create-name"
                      placeholder="e.g. Website widget"
                      value={createForm.name}
                      onChange={(e) =>
                        setCreateForm((f) => ({ ...f, name: e.target.value }))
                      }
                      required
                      autoFocus
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="create-rate-limit">
                      Rate limit per minute (optional)
                    </Label>
                    <Input
                      id="create-rate-limit"
                      type="number"
                      min={1}
                      placeholder="Uses server default if empty"
                      value={createForm.rateLimitPerMinute}
                      onChange={(e) =>
                        setCreateForm((f) => ({
                          ...f,
                          rateLimitPerMinute: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <DialogFooter>
                    <Button type="submit" disabled={creating}>
                      {creating ? <Loader2Icon className="animate-spin" /> : null}
                      Create key
                    </Button>
                  </DialogFooter>
                </form>
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>App name</TableHead>
              <TableHead>Key prefix</TableHead>
              <TableHead>Rate limit / min</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  Loading API keys...
                </TableCell>
              </TableRow>
            ) : sortedKeys.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  No API keys yet. Create one to allow an app to call the webhook.
                </TableCell>
              </TableRow>
            ) : (
              sortedKeys.map((apiKey) => {
                const revoked = !!apiKey.revoked_at;
                return (
                  <TableRow key={apiKey.id}>
                    <TableCell className="font-medium">
                      <span className="flex items-center gap-1.5">
                        <KeyRoundIcon className="size-3.5 text-muted-foreground" />
                        {apiKey.name}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-muted-foreground">
                      {apiKey.key_prefix}…
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {apiKey.rate_limit_per_minute ?? "default"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={revoked ? "destructive" : "secondary"}>
                        {revoked ? "Revoked" : "Active"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(apiKey.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={revoked}
                        onClick={() => setRevokeTarget(apiKey)}
                      >
                        Revoke
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <AlertDialog
        open={!!revokeTarget}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API key?</AlertDialogTitle>
            <AlertDialogDescription>
              &quot;{revokeTarget?.name}&quot; will no longer be able to call the
              webhook. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/80"
              onClick={handleRevoke}
              disabled={revoking}
            >
              {revoking ? <Loader2Icon className="animate-spin" /> : null}
              Revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
