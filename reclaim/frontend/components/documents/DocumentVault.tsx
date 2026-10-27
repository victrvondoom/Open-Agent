"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Upload, FileText, Search, Grid3X3, List, Download, Trash2, X, Loader2,
  CheckCircle2, AlertCircle, Clock, FileWarning, ExternalLink,
} from "lucide-react";
import {
  listDocuments, uploadDocument, deleteDocument, getDocumentSignedUrl, type VaultDocument,
} from "@/lib/api-client";
import { DOMAIN_THEME, domainTheme } from "@/components/chat/domain-theme";

const DOC_TYPE_LABELS: Record<string, string> = {
  policy: "Policy Contract",
  medical_report: "Medical Record",
  rejection_letter: "Rejection Letter",
  bill: "Invoice / Bill",
  other: "Evidence Document",
};

function formatSize(bytes: number): string {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

interface PendingUpload {
  id: string;
  filename: string;
  progress: number;
  error?: string;
}

export function DocumentVault() {
  const [documents, setDocuments] = useState<VaultDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [uploadDomain, setUploadDomain] = useState<string>("health_insurance");
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [selected, setSelected] = useState<VaultDocument | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // keep last-known list
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const handleFiles = useCallback(
    async (fileList: FileList) => {
      const files = Array.from(fileList);
      for (const file of files) {
        const uploadId = crypto.randomUUID();
        const pending: PendingUpload = { id: uploadId, filename: file.name, progress: 10 };
        setPendingUploads((curr) => [...curr, pending]);

        try {
          await uploadDocument(uploadDomain, file, {
            onProgress: (pct: number) => {
              setPendingUploads((curr) =>
                curr.map((p) => (p.id === uploadId ? { ...p, progress: pct } : p))
              );
            },
          });
          setPendingUploads((curr) => curr.filter((p) => p.id !== uploadId));
          await refresh();
        } catch (err) {
          setPendingUploads((curr) =>
            curr.map((p) =>
              p.id === uploadId
                ? { ...p, error: err instanceof Error ? err.message : "Upload failed" }
                : p
            )
          );
        }
      }
    },
    [uploadDomain]
  );

  async function handleDelete(doc: VaultDocument) {
    if (!window.confirm(`Delete "${doc.filename}" from the vault?`)) return;
    setDocuments((curr) => curr.filter((d) => d.id !== doc.id));
    if (selected?.id === doc.id) setSelected(null);
    try {
      await deleteDocument(doc.document_id);
    } catch {
      refresh();
    }
  }

  const filtered = useMemo(() => {
    return documents.filter((d) => {
      if (domainFilter !== "all" && d.domain !== domainFilter) return false;
      if (typeFilter !== "all" && d.document_type !== typeFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          d.filename.toLowerCase().includes(q) ||
          (d.text_extract ?? "").toLowerCase().includes(q) ||
          (d.domain ?? "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [documents, domainFilter, typeFilter, search]);

  return (
    <div
      className="relative flex flex-1 flex-col gap-4"
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragActive(false);
        if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
      }}
    >
      {dragActive && (
        <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center rounded-xl border-2 border-dashed border-[#231f1d] bg-amber-100/90 shadow-[4px_4px_0_#231f1d]">
          <div className="text-center">
            <Upload className="mx-auto mb-2 size-10 text-stone-900" />
            <p className="font-mono text-sm font-black uppercase text-stone-900">Drop files to add evidence</p>
          </div>
        </div>
      )}

      <UploadBar
        uploadDomain={uploadDomain}
        setUploadDomain={setUploadDomain}
        onPick={() => fileInputRef.current?.click()}
        pendingUploads={pendingUploads}
      />
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.csv,.json,image/*"
        className="hidden"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
      />

      <div className="flex flex-wrap items-center gap-2 rounded-xl border-2 border-[#231f1d] bg-white p-3 shadow-[3px_3px_0_#231f1d]">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents by content, filename, or domain..."
            className="w-full rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] py-1.5 pl-8 pr-2 text-xs font-medium text-stone-900 outline-none shadow-[1.5px_1.5px_0_#231f1d] focus:border-amber-600 placeholder:text-stone-400"
          />
        </div>
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="rounded-lg border-2 border-[#231f1d] bg-white px-2 py-1.5 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
        >
          <option value="all">All Domains</option>
          {Object.entries(DOMAIN_THEME).map(([key, theme]) => (
            <option key={key} value={key}>{theme.label}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border-2 border-[#231f1d] bg-white px-2 py-1.5 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
        >
          <option value="all">All Types</option>
          {Object.entries(DOC_TYPE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <span className="ml-auto font-mono text-[10px] font-bold text-stone-600">
          {filtered.length} document{filtered.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="flex flex-1 gap-4">
        <div className="flex-1">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-stone-500 py-12">
              <Loader2 className="size-6 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex h-60 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-stone-300 bg-white p-8 text-center">
              <FileText className="size-8 text-stone-400" />
              <p className="text-xs font-medium text-stone-600">
                {documents.length === 0 ? "No documents in vault yet -- drag files or click Upload Documents." : "No documents match your filters."}
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} onOpen={() => setSelected(doc)} onDelete={() => handleDelete(doc)} />
              ))}
            </div>
          )}
        </div>

        {selected && <DocumentDetail doc={selected} onClose={() => setSelected(null)} onDelete={() => handleDelete(selected)} />}
      </div>
    </div>
  );
}

function UploadBar({
  uploadDomain, setUploadDomain, onPick, pendingUploads,
}: {
  uploadDomain: string;
  setUploadDomain: (v: string) => void;
  onPick: () => void;
  pendingUploads: PendingUpload[];
}) {
  return (
    <div className="rounded-xl border-2 border-[#231f1d] bg-white p-4 shadow-[4px_4px_0_#231f1d]">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onPick}
          className="pixel-btn-primary inline-flex items-center gap-2 px-4 py-2 text-xs uppercase tracking-wide"
        >
          <Upload className="size-4" /> Upload Documents
        </button>
        <select
          value={uploadDomain}
          onChange={(e) => setUploadDomain(e.target.value)}
          className="rounded-lg border-2 border-[#231f1d] bg-white px-3 py-1.5 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
        >
          {Object.entries(DOMAIN_THEME).map(([key, theme]) => (
            <option key={key} value={key}>{theme.label}</option>
          ))}
        </select>
        <p className="font-mono text-[10px] text-stone-500">PDF, text, images (up to 10MB) &middot; multi-page OCR &middot; vector indexing</p>
      </div>

      {pendingUploads.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {pendingUploads.map((upload) => (
            <div key={upload.id} className="rounded-lg border-2 border-[#231f1d] bg-[#fbf9f2] p-2 shadow-[1.5px_1.5px_0_#231f1d]">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="truncate font-medium text-stone-900">{upload.filename}</span>
                {upload.error ? (
                  <span className="flex items-center gap-1 font-bold text-red-600"><AlertCircle className="size-3" /> Failed</span>
                ) : (
                  <span className="font-mono text-stone-600">{upload.progress}%</span>
                )}
              </div>
              {!upload.error && (
                <div className="h-1.5 overflow-hidden rounded-full border border-[#231f1d] bg-stone-200">
                  <div className="h-full bg-amber-500 transition-all" style={{ width: `${upload.progress}%` }} />
                </div>
              )}
              {upload.error && <p className="mt-1 text-[10px] font-bold text-red-600">{upload.error}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DocumentCard({ doc, onOpen, onDelete }: { doc: VaultDocument; onOpen: () => void; onDelete: () => void }) {
  const theme = domainTheme(doc.domain ?? "");
  return (
    <div className="group rounded-xl border-2 border-[#231f1d] bg-white p-4 shadow-[3px_3px_0_#231f1d] transition-transform hover:-translate-y-0.5 hover:shadow-[4.5px_4.5px_0_#231f1d]">
      <div className="mb-3 flex items-start justify-between">
        <div className="grid size-10 place-items-center rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] shadow-[1.5px_1.5px_0_#231f1d]" style={{ borderColor: theme.color }}>
          <FileText className="size-5" style={{ color: theme.color }} />
        </div>
        <button onClick={onDelete} className="pixel-btn p-1 text-stone-400 hover:text-red-600" title="Delete document">
          <Trash2 className="size-3.5" />
        </button>
      </div>
      <button onClick={onOpen} className="text-left w-full">
        <p className="line-clamp-1 text-xs font-bold text-stone-900 hover:text-amber-700">{doc.filename}</p>
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-[#231f1d] px-2 py-0.5 text-[9px] font-mono font-bold shadow-[1px_1px_0_#231f1d]" style={{ backgroundColor: "#fcfaf5", color: theme.color }}>
          {theme.label}
        </span>
        <span className="rounded border border-[#231f1d] bg-white px-2 py-0.5 text-[9px] font-mono font-bold text-stone-700 shadow-[1px_1px_0_#231f1d]">
          {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between font-mono text-[10px] text-stone-500">
        <span className="flex items-center gap-1"><Clock className="size-3" />{timeAgo(doc.created_at)}</span>
        <span>{formatSize(doc.size_bytes)}</span>
      </div>
      <div className="mt-3 flex items-center justify-between border-t-2 border-stone-200 pt-2.5">
        {doc.indexed ? (
          <span className="flex items-center gap-1 font-mono text-[10px] font-bold text-emerald-700">
            <CheckCircle2 className="size-3" /> Indexed ({doc.chunks_indexed} chunks)
          </span>
        ) : (
          <span className="flex items-center gap-1 font-mono text-[10px] font-bold text-amber-700">
            <FileWarning className="size-3" /> Processing
          </span>
        )}
        <button onClick={onOpen} className="font-mono text-[10px] font-black text-amber-800 hover:underline">
          View &rarr;
        </button>
      </div>
    </div>
  );
}

function DocumentDetail({ doc, onClose, onDelete }: { doc: VaultDocument; onClose: () => void; onDelete: () => void }) {
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const theme = domainTheme(doc.domain ?? "");

  async function handleDownload() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const url = await getDocumentSignedUrl(doc.case_id, doc.document_id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      setDownloadError("Original file storage isn't available in this environment -- displaying extracted text below.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex w-full max-w-md flex-col rounded-xl border-2 border-[#231f1d] bg-white shadow-[4px_4px_0_#231f1d] xl:w-[420px] overflow-hidden">
      <div className="flex items-center justify-between border-b-2 border-stone-200 p-4 bg-[#fbf9f2]" style={{ borderTop: `4px solid ${theme.color}` }}>
        <div className="min-w-0">
          <p className="truncate text-xs font-black font-mono text-stone-900">{doc.filename}</p>
          <p className="font-mono text-[10px] text-stone-500">{theme.label} &middot; {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}</p>
        </div>
        <button onClick={onClose} className="pixel-btn p-1 text-stone-700 hover:bg-stone-200">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex items-center gap-2 border-b-2 border-stone-200 p-3 bg-white">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="pixel-btn inline-flex items-center gap-1.5 px-3 py-1 text-xs"
        >
          {downloading ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />} Download file
        </button>
        <button
          onClick={onDelete}
          className="pixel-btn ml-auto inline-flex items-center gap-1.5 px-3 py-1 text-xs text-red-700"
        >
          <Trash2 className="size-3.5" /> Delete
        </button>
      </div>
      {downloadError && (
        <p className="border-b-2 border-amber-200 bg-amber-50 px-4 py-2 font-mono text-[10px] text-amber-900">{downloadError}</p>
      )}

      <div className="flex-1 overflow-y-auto p-4 bg-[#fcfaf5]">
        <p className="mb-2 font-mono text-[10px] font-black uppercase tracking-wider text-stone-700">Extracted statutory content</p>
        {doc.text_extract ? (
          <pre className="whitespace-pre-wrap break-words rounded-lg border-2 border-[#231f1d] bg-white p-3 font-mono text-xs leading-5 text-stone-900 shadow-[2px_2px_0_#231f1d]">
            {doc.text_extract}
          </pre>
        ) : (
          <p className="text-xs text-stone-500 font-mono">No text could be extracted from this file. Try a clear document scan or searchable PDF.</p>
        )}
      </div>
    </div>
  );
}
