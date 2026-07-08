"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { FileText, Loader2Icon, PencilIcon, Plus, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { ApiError, createDomain, deleteDomain, listDomains, updateDomain } from "@/lib/api";
import type { Domain } from "@/lib/types";

interface DomainFormState {
  name: string;
  slug: string;
  description: string;
}

const EMPTY_FORM: DomainFormState = { name: "", slug: "", description: "" };

export default function DomainsPage() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<DomainFormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);

  const [editTarget, setEditTarget] = useState<Domain | null>(null);
  const [editForm, setEditForm] = useState<DomainFormState>(EMPTY_FORM);
  const [editing, setEditing] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Domain | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listDomains();
      setDomains(data);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401) {
        toast.error("Failed to load domains", { description: err.message });
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
        const data = await listDomains();
        if (!cancelled) setDomains(data);
      } catch (err) {
        if (!cancelled && err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load domains", { description: err.message });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedDomains = useMemo(
    () =>
      [...domains].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ),
    [domains]
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    try {
      await createDomain({
        name: createForm.name.trim(),
        slug: createForm.slug.trim() || undefined,
        description: createForm.description.trim() || undefined,
      });
      toast.success("Domain created");
      setCreateOpen(false);
      setCreateForm(EMPTY_FORM);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 409 ? "A domain with that name or slug already exists" : "Failed to create domain",
          { description: err.message }
        );
      }
    } finally {
      setCreating(false);
    }
  }

  function openEdit(domain: Domain) {
    setEditTarget(domain);
    setEditForm({
      name: domain.name,
      slug: domain.slug,
      description: domain.description ?? "",
    });
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editTarget) return;
    setEditing(true);
    try {
      await updateDomain(editTarget.id, {
        name: editForm.name.trim(),
        slug: editForm.slug.trim() || undefined,
        description: editForm.description.trim() || undefined,
      });
      toast.success("Domain updated");
      setEditTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 409 ? "A domain with that name or slug already exists" : "Failed to update domain",
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
      await deleteDomain(deleteTarget.id);
      toast.success("Domain deleted");
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to delete domain", { description: err.message });
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Domains</h1>
          <p className="text-sm text-muted-foreground">
            Manage knowledge domains and their documents.
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger render={<Button><Plus />New domain</Button>} />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New domain</DialogTitle>
              <DialogDescription>
                Create a new knowledge domain for your chatbot.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="create-name">Name</Label>
                <Input
                  id="create-name"
                  value={createForm.name}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, name: e.target.value }))
                  }
                  required
                  autoFocus
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="create-slug">Slug (optional)</Label>
                <Input
                  id="create-slug"
                  placeholder="auto-generated from name"
                  value={createForm.slug}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, slug: e.target.value }))
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="create-description">Description</Label>
                <Textarea
                  id="create-description"
                  value={createForm.description}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, description: e.target.value }))
                  }
                  rows={3}
                />
              </div>
              <DialogFooter>
                <Button type="submit" disabled={creating}>
                  {creating ? <Loader2Icon className="animate-spin" /> : null}
                  Create domain
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  Loading domains...
                </TableCell>
              </TableRow>
            ) : sortedDomains.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  No domains yet. Create one to get started.
                </TableCell>
              </TableRow>
            ) : (
              sortedDomains.map((domain) => (
                <TableRow key={domain.id}>
                  <TableCell className="font-medium">
                    <Link
                      href={`/domains/${domain.id}`}
                      className="hover:underline"
                    >
                      {domain.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{domain.slug}</TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground">
                    {domain.description || "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(domain.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="icon-sm" render={<Link href={`/domains/${domain.id}`} />} aria-label="Documents">
                        <FileText />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Edit"
                        onClick={() => openEdit(domain)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Delete"
                        onClick={() => setDeleteTarget(domain)}
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

      <Dialog open={!!editTarget} onOpenChange={(open) => !open && setEditTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit domain</DialogTitle>
            <DialogDescription>Update the domain&apos;s details.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEdit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={editForm.name}
                onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="edit-slug">Slug</Label>
              <Input
                id="edit-slug"
                value={editForm.slug}
                onChange={(e) => setEditForm((f) => ({ ...f, slug: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="edit-description">Description</Label>
              <Textarea
                id="edit-description"
                value={editForm.description}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, description: e.target.value }))
                }
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={editing}>
                {editing ? <Loader2Icon className="animate-spin" /> : null}
                Save changes
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete domain?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{deleteTarget?.name}&quot; and all of
              its documents. This action cannot be undone.
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
