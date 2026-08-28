"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  ArrowLeftIcon,
  FileIcon,
  Loader2Icon,
  Trash2Icon,
  UploadIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
  deleteDocument,
  getKnowledgeBase,
  listDocuments,
  uploadDocument,
} from "@/lib/api";
import type { Document, DocumentStatus, KnowledgeBase } from "@/lib/types";
import { cn } from "@/lib/utils";
import { resolveOrgId } from "@/lib/org";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];
const SETTLED_STATUSES: DocumentStatus[] = ["completed", "failed"];

function statusBadgeVariant(
  status: DocumentStatus
): "default" | "secondary" | "outline" | "destructive" {
  switch (status) {
    case "completed":
      return "default";
    case "processing":
      return "outline";
    case "failed":
      return "destructive";
    default:
      return "secondary";
  }
}

export default function KBDocumentsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const [orgId, setOrgId] = useState<string | null>(null);
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const refreshDocuments = useCallback(
    async (orgIdParam: string) => {
      try {
        const docs = await listDocuments(orgIdParam, id);
        setDocuments(docs);
      } catch (err) {
        if (err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load documents", { description: err.message });
        }
      }
    },
    [id]
  );

  useEffect(() => {
    if (!orgId) return;

    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [kbResult, docsResult] = await Promise.allSettled([
          getKnowledgeBase(orgId!, id),
          listDocuments(orgId!, id),
        ]);
        if (cancelled) return;

        if (kbResult.status === "fulfilled") setKb(kbResult.value);
        if (docsResult.status === "fulfilled") setDocuments(docsResult.value);

        for (const [label, result] of [
          ["knowledge base", kbResult],
          ["documents", docsResult],
        ] as const) {
          if (result.status === "rejected") {
            const err = result.reason;
            if (err instanceof ApiError && err.status !== 401) {
              toast.error(`Failed to load ${label}`, { description: err.message });
            }
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [orgId, id]);

  useEffect(() => {
    if (!orgId) return;

    const hasUnsettled = documents.some(
      (doc) => !SETTLED_STATUSES.includes(doc.status)
    );

    if (hasUnsettled && !pollRef.current) {
      pollRef.current = setInterval(() => refreshDocuments(orgId!), 3000);
    } else if (!hasUnsettled && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, refreshDocuments, orgId]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0 || !orgId) return;
    const file = files[0];
    const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      toast.error("Unsupported file type", {
        description: `Accepted types: ${ACCEPTED_EXTENSIONS.join(", ")}`,
      });
      return;
    }

    setUploading(true);
    try {
      await uploadDocument(orgId!, id, file);
      toast.success("Document uploaded, processing started");
      refreshDocuments(orgId!);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(
          err.status === 415 ? "Unsupported file type" : "Upload failed",
          { description: err.message }
        );
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete() {
    if (!deleteTarget || !orgId) return;
    setDeleting(true);
    try {
      await deleteDocument(orgId!, id, deleteTarget.id);
      toast.success("Document deleted");
      setDeleteTarget(null);
      refreshDocuments(orgId!);
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to delete document", { description: err.message });
      }
    } finally {
      setDeleting(false);
    }
  }

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <Button
          variant="ghost"
          size="sm"
          render={<Link href="/domains" />}
          nativeButton={false}
          className="mb-2 -ml-2"
        >
          <ArrowLeftIcon />
          Back to knowledge bases
        </Button>
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button
          variant="ghost"
          size="sm"
          render={<Link href="/domains" />}
          nativeButton={false}
          className="mb-2 -ml-2"
        >
          <ArrowLeftIcon />
          Back to knowledge bases
        </Button>
        {loading ? (
          <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        ) : (
          <>
            <h1 className="font-heading text-3xl tracking-tight">
              {kb?.name ?? "Knowledge Base"}
            </h1>
            {kb?.description ? (
              <p className="text-sm text-muted-foreground">{kb.description}</p>
            ) : null}
          </>
        )}
      </div>

      <div
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          dragActive ? "border-primary bg-primary/5" : "border-border"
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <UploadIcon className="size-6 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium">
            Drag and drop a file here, or click to browse
          </p>
          <p className="text-xs text-muted-foreground">
            Accepted formats: {ACCEPTED_EXTENSIONS.join(", ")}
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <Button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? <Loader2Icon className="animate-spin" /> : <UploadIcon />}
          Upload document
        </Button>
      </div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Filename</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  Loading documents...
                </TableCell>
              </TableRow>
            ) : documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-14 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <FileIcon className="size-6 opacity-50" />
                    <p className="text-sm">No documents uploaded yet.</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              documents.map((doc) => (
                <TableRow
                  key={doc.id}
                  className="border-l-2 border-l-transparent transition-colors hover:border-l-primary hover:bg-accent/30"
                >
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      <FileIcon className="size-4 text-muted-foreground" />
                      {doc.filename}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {doc.mime_type}
                  </TableCell>
                  <TableCell>
                    {doc.status === "failed" && doc.error ? (
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <Badge
                              variant={statusBadgeVariant(doc.status)}
                              className="cursor-help"
                            />
                          }
                        >
                          {doc.status}
                        </TooltipTrigger>
                        <TooltipContent>{doc.error}</TooltipContent>
                      </Tooltip>
                    ) : (
                      <Badge
                        variant={statusBadgeVariant(doc.status)}
                        className={cn(
                          doc.status === "processing" && "animate-pulse"
                        )}
                      >
                        {doc.status}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(doc.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Delete document"
                      onClick={() => setDeleteTarget(doc)}
                    >
                      <Trash2Icon />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &quot;{deleteTarget?.filename}&quot;.
              This action cannot be undone.
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
