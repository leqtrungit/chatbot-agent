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
  getDomain,
  listDocuments,
  uploadDocument,
} from "@/lib/api";
import type { Document, DocumentStatus, Domain } from "@/lib/types";
import { cn } from "@/lib/utils";

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

export default function DomainDocumentsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const [domain, setDomain] = useState<Domain | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null);
  const [deleting, setDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshDocuments = useCallback(async () => {
    try {
      const docs = await listDocuments(id);
      setDocuments(docs);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401) {
        toast.error("Failed to load documents", { description: err.message });
      }
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [domainData, docs] = await Promise.all([
          getDomain(id),
          listDocuments(id),
        ]);
        if (!cancelled) {
          setDomain(domainData);
          setDocuments(docs);
        }
      } catch (err) {
        if (err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load domain", { description: err.message });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    const hasUnsettled = documents.some(
      (doc) => !SETTLED_STATUSES.includes(doc.status)
    );

    if (hasUnsettled && !pollRef.current) {
      pollRef.current = setInterval(refreshDocuments, 3000);
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
  }, [documents, refreshDocuments]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
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
      await uploadDocument(id, file);
      toast.success("Document uploaded, processing started");
      refreshDocuments();
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
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteDocument(deleteTarget.id);
      toast.success("Document deleted");
      setDeleteTarget(null);
      refreshDocuments();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error("Failed to delete document", { description: err.message });
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button
          variant="ghost"
          size="sm"
          render={<Link href="/domains" />}
          className="mb-2 -ml-2"
        >
          <ArrowLeftIcon />
          Back to domains
        </Button>
        {loading ? (
          <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        ) : (
          <>
            <h1 className="text-2xl font-semibold tracking-tight">
              {domain?.name ?? "Domain"}
            </h1>
            {domain?.description ? (
              <p className="text-sm text-muted-foreground">{domain.description}</p>
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
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  No documents uploaded yet.
                </TableCell>
              </TableRow>
            ) : (
              documents.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      <FileIcon className="size-4 text-muted-foreground" />
                      {doc.filename}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
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
