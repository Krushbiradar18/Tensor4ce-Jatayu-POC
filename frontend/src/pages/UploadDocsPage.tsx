import { useState, useCallback, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Upload, FileText, CheckCircle2, AlertCircle, X, ArrowRight, Loader2,
  CreditCard, Building2, Receipt, FileBadge,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

// ── Types ─────────────────────────────────────────────────────────────────────

type DocKey = "aadhaar" | "pan" | "bank_statement" | "salary_slip";
type UploadStatus = "idle" | "uploading" | "done" | "error";

interface DocSlot {
  key: DocKey;
  label: string;
  description: string;
  note: string;
  icon: React.ElementType;
  required: boolean;
  accept: string;
}

interface DocState {
  file: File | null;
  status: UploadStatus;
  result: Record<string, unknown> | null;
  error: string | null;
}

// ── Document slot definitions ─────────────────────────────────────────────────

const DOC_SLOTS: DocSlot[] = [
  {
    key: "aadhaar",
    label: "Aadhaar Card",
    description: "Your Government-issued Aadhaar card (front & back)",
    note: "Upload front side; back side optional",
    icon: CreditCard,
    required: true,
    accept: ".pdf,.jpg,.jpeg,.png",
  },
  {
    key: "pan",
    label: "PAN Card",
    description: "Permanent Account Number (PAN) card",
    note: "Clear scan or photo — all 10 characters must be visible",
    icon: FileBadge,
    required: true,
    accept: ".pdf,.jpg,.jpeg,.png",
  },
  {
    key: "bank_statement",
    label: "Bank Statement (6 months)",
    description: "Latest 6-month bank account statement",
    note: "PDF from your bank preferred for accurate extraction",
    icon: Building2,
    required: true,
    accept: ".pdf",
  },
  {
    key: "salary_slip",
    label: "Salary Slips / Form 16",
    description: "3 months salary slips or latest Form 16",
    note: "If salaried: 3 recent payslips. Others: Form 16 / ITR",
    icon: Receipt,
    required: false,
    accept: ".pdf,.jpg,.jpeg,.png",
  },
];

// ── API helper ────────────────────────────────────────────────────────────────

async function uploadDocument(
  appId: string,
  docType: string,
  file: File
): Promise<Record<string, unknown>> {
  const fd = new FormData();
  fd.append("doc_type", docType);
  fd.append("file", file);

  const res = await fetch(`/api/upload/${appId}`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }

  return res.json();
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function UploadDocsPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const appId = params.get("id") || "";

  const initState = (): Record<DocKey, DocState> => ({
    aadhaar:       { file: null, status: "idle", result: null, error: null },
    pan:           { file: null, status: "idle", result: null, error: null },
    bank_statement:{ file: null, status: "idle", result: null, error: null },
    salary_slip:   { file: null, status: "idle", result: null, error: null },
  });

  const [docs, setDocs] = useState<Record<DocKey, DocState>>(initState);
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const setDoc = (key: DocKey, patch: Partial<DocState>) =>
    setDocs((d) => ({ ...d, [key]: { ...d[key], ...patch } }));

  // ── File selection ──────────────────────────────────────────────────────────
  const handleFileChange = (key: DocKey, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file) {
      setDoc(key, { file, status: "idle", result: null, error: null });
    }
  };

  const handleDrop = useCallback(
    (key: DocKey, e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) setDoc(key, { file, status: "idle", result: null, error: null });
    },
    []
  );

  // ── Single upload ───────────────────────────────────────────────────────────
  const handleUpload = async (slot: DocSlot) => {
    const doc = docs[slot.key];
    if (!doc.file) return;
    if (!appId) {
      toast({ title: "Error", description: "No application ID found.", variant: "destructive" });
      return;
    }

    setDoc(slot.key, { status: "uploading", error: null });
    try {
      const result = await uploadDocument(appId, slot.key, doc.file);
      setDoc(slot.key, { status: "done", result });
      toast({ title: "Uploaded", description: `${slot.label} processed successfully.` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setDoc(slot.key, { status: "error", error: msg });
      toast({ title: "Upload Failed", description: msg, variant: "destructive" });
    }
  };

  // ── Check readiness ─────────────────────────────────────────────────────────
  const requiredDone = DOC_SLOTS.filter((s) => s.required).every(
    (s) => docs[s.key].status === "done"
  );

  const anyPending = DOC_SLOTS.some(
    (s) => docs[s.key].file && docs[s.key].status === "idle"
  );

  // ── Upload all pending ──────────────────────────────────────────────────────
  const handleUploadAll = async () => {
    const pending = DOC_SLOTS.filter(
      (s) => docs[s.key].file && docs[s.key].status === "idle"
    );
    for (const slot of pending) {
      await handleUpload(slot);
    }
  };

  // ── Extracted field display ─────────────────────────────────────────────────
  const renderExtracted = (result: Record<string, unknown> | null) => {
    if (!result) return null;
    const fields = result.extracted_fields as Record<string, unknown> | undefined;
    if (!fields || typeof fields !== "object") return null;

    const visible = Object.entries(fields).filter(
      ([k, v]) =>
        v !== null &&
        v !== undefined &&
        v !== "" &&
        !k.startsWith("_") &&
        k !== "sample_transactions" &&
        k !== "confidence"
    );
    if (!visible.length) return null;

    return (
      <div className="mt-3 rounded-lg bg-success/5 border border-success/20 p-3 text-sm space-y-1">
        <p className="text-xs font-semibold text-success mb-2">Extracted Fields</p>
        {visible.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <span className="text-muted-foreground capitalize">
              {k.replace(/_/g, " ")}
            </span>
            <span className="text-foreground font-mono text-xs truncate max-w-[55%] text-right">
              {String(v)}
            </span>
          </div>
        ))}
      </div>
    );
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-10 max-w-4xl">
        {/* Header */}
        <div className="text-center mb-10 animate-fade-in">
          <h1 className="text-3xl font-bold font-display text-foreground mb-2">
            Upload Documents
          </h1>
          {appId && (
            <p className="text-sm text-muted-foreground">
              Application{" "}
              <span className="font-mono text-primary font-semibold">{appId}</span>
            </p>
          )}
          <p className="text-muted-foreground mt-2 max-w-xl mx-auto">
            Upload your KYC and financial documents. Files are processed locally
            using OCR — we never store raw file contents.
          </p>
        </div>

        {/* Progress badges */}
        <div className="flex flex-wrap gap-2 justify-center mb-8">
          {DOC_SLOTS.map((s) => {
            const st = docs[s.key].status;
            return (
              <Badge
                key={s.key}
                className={
                  st === "done"
                    ? "bg-success/15 text-success border-success/30"
                    : st === "uploading"
                    ? "bg-info/15 text-info border-info/30"
                    : st === "error"
                    ? "bg-destructive/15 text-destructive border-destructive/30"
                    : docs[s.key].file
                    ? "bg-warning/15 text-warning-foreground border-warning/30"
                    : "bg-muted text-muted-foreground"
                }
                variant="outline"
              >
                {st === "done" && <CheckCircle2 className="h-3 w-3 mr-1" />}
                {st === "uploading" && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                {st === "error" && <AlertCircle className="h-3 w-3 mr-1" />}
                {s.label}
                {s.required && st !== "done" && (
                  <span className="ml-1 text-destructive">*</span>
                )}
              </Badge>
            );
          })}
        </div>

        {/* Document cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {DOC_SLOTS.map((slot) => {
            const doc = docs[slot.key];
            const Icon = slot.icon;

            return (
              <Card
                key={slot.key}
                className={`shadow-card transition-all ${
                  doc.status === "done"
                    ? "border-success/40"
                    : doc.status === "error"
                    ? "border-destructive/40"
                    : "hover:shadow-elevated"
                }`}
              >
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2 font-display">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        doc.status === "done"
                          ? "bg-success/15"
                          : doc.status === "error"
                          ? "bg-destructive/15"
                          : "bg-primary/10"
                      }`}
                    >
                      {doc.status === "done" ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : doc.status === "error" ? (
                        <AlertCircle className="h-4 w-4 text-destructive" />
                      ) : (
                        <Icon className="h-4 w-4 text-primary" />
                      )}
                    </div>
                    {slot.label}
                    {slot.required && (
                      <span className="text-xs text-destructive ml-1">Required</span>
                    )}
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">{slot.description}</p>
                </CardHeader>

                <CardContent className="space-y-3">
                  {/* Drop zone */}
                  {doc.status !== "done" && (
                    <div
                      className="border-2 border-dashed border-border rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => handleDrop(slot.key, e)}
                      onClick={() => inputRefs.current[slot.key]?.click()}
                    >
                      <input
                        ref={(el) => { inputRefs.current[slot.key] = el; }}
                        type="file"
                        accept={slot.accept}
                        className="hidden"
                        onChange={(e) => handleFileChange(slot.key, e)}
                      />
                      {doc.file ? (
                        <div className="flex items-center justify-center gap-2">
                          <FileText className="h-5 w-5 text-primary" />
                          <span className="text-sm text-foreground font-medium truncate max-w-[180px]">
                            {doc.file.name}
                          </span>
                          <button
                            className="text-muted-foreground hover:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDoc(slot.key, { file: null, status: "idle", result: null, error: null });
                              if (inputRefs.current[slot.key]) {
                                inputRefs.current[slot.key]!.value = "";
                              }
                            }}
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <Upload className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                          <p className="text-sm text-muted-foreground">
                            Drop file here or{" "}
                            <span className="text-primary font-medium">click to browse</span>
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {slot.accept.replace(/\./g, "").toUpperCase().replace(/,/g, ", ")} &bull; max 10 MB
                          </p>
                        </>
                      )}
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground">{slot.note}</p>

                  {/* Error message */}
                  {doc.status === "error" && doc.error && (
                    <div className="flex items-start gap-2 bg-destructive/10 rounded p-2 text-xs text-destructive">
                      <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                      {doc.error}
                    </div>
                  )}

                  {/* Upload button */}
                  {doc.file && doc.status !== "done" && (
                    <Button
                      size="sm"
                      className="w-full"
                      disabled={doc.status === "uploading"}
                      onClick={() => handleUpload(slot)}
                    >
                      {doc.status === "uploading" ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Processing…
                        </>
                      ) : (
                        <>
                          <Upload className="h-4 w-4 mr-2" />
                          Upload & Extract
                        </>
                      )}
                    </Button>
                  )}

                  {/* Success with extracted fields */}
                  {doc.status === "done" && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm text-success">
                        <CheckCircle2 className="h-4 w-4" />
                        <span>{doc.file?.name}</span>
                        <span className="text-xs text-muted-foreground ml-auto">
                          via {(doc.result?.extraction_method as string) || "OCR"}
                        </span>
                      </div>
                      {renderExtracted(doc.result)}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Footer actions */}
        <div className="flex flex-col sm:flex-row gap-3 justify-between items-center bg-card rounded-lg border border-border p-4 shadow-card">
          <div className="text-sm text-muted-foreground">
            {requiredDone ? (
              <span className="text-success font-medium flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4" /> All required documents uploaded
              </span>
            ) : (
              <span>
                {DOC_SLOTS.filter((s) => s.required && docs[s.key].status !== "done").length} required
                document(s) remaining
              </span>
            )}
          </div>

          <div className="flex gap-3">
            {anyPending && (
              <Button variant="outline" onClick={handleUploadAll}>
                <Upload className="h-4 w-4 mr-2" />
                Upload All Pending
              </Button>
            )}
            <Button
              disabled={!requiredDone}
              onClick={() => navigate(`/apply/success?id=${appId}`)}
            >
              Continue <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </div>
        </div>

        {!requiredDone && (
          <p className="text-center text-xs text-muted-foreground mt-4">
            You can also{" "}
            <button
              className="text-primary underline underline-offset-2"
              onClick={() => navigate(`/apply/success?id=${appId}`)}
            >
              skip for now
            </button>{" "}
            and upload later.
          </p>
        )}
      </div>
    </PublicLayout>
  );
}
