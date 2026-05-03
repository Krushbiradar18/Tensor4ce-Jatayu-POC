import { useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, Loader2, Activity, ShieldCheck, CheckCircle2, FileWarning, AlertCircle, Upload, RefreshCw } from "lucide-react";
import { getApplicationStatus, resubmitDocuments } from "@/lib/api";

const statusColors: Record<string, string> = {
  "PENDING": "bg-primary/10 text-primary border-primary/20",
  "DIL_PROCESSING": "bg-primary/10 text-primary border-primary/20",
  "AGENTS_RUNNING": "bg-accent/10 text-accent border-accent/20 animate-pulse",
  "DECIDED_PENDING_OFFICER": "bg-accent/10 text-accent border-accent/20",
  "DATA_REQUIRED": "bg-warning/10 text-warning border-warning/20",
  "OFFICER_APPROVED": "bg-success/10 text-success border-success/20",
  "OFFICER_REJECTED": "bg-destructive/10 text-destructive border-destructive/20",
  "OFFICER_CONDITIONAL": "bg-warning/10 text-warning border-warning/20",
  "OFFICER_ESCALATED": "bg-warning/10 text-warning border-warning/20",
};

export default function TrackPage() {
  const [params] = useSearchParams();
  const [searchId, setSearchId] = useState(params.get("id") || "");
  const [app, setApp] = useState<any>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);

  // Resubmit state
  const [resubmitIncome, setResubmitIncome] = useState("");
  const [resubmitFiles, setResubmitFiles] = useState<{
    bankStatement?: File; salarySlip?: File; itr?: File;
  }>({});
  const [resubmitLoading, setResubmitLoading] = useState(false);
  const [resubmitDone, setResubmitDone] = useState(false);
  const bankRef = useRef<HTMLInputElement>(null);
  const salaryRef = useRef<HTMLInputElement>(null);
  const itrRef = useRef<HTMLInputElement>(null);

  const handleSearch = async () => {
    if (!searchId.trim()) return;
    setLoading(true);
    setNotFound(false);
    setApp(null);
    setResubmitDone(false);

    try {
      const result = await getApplicationStatus(searchId.trim());
      setApp(result);
    } catch (error) {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  };

  const handleResubmit = async () => {
    if (!app?.application_id) return;
    setResubmitLoading(true);
    try {
      const income = resubmitIncome ? parseFloat(resubmitIncome) : null;
      await resubmitDocuments(app.application_id, income, resubmitFiles);
      setResubmitDone(true);
      // Refresh status after a brief pause
      setTimeout(async () => {
        const updated = await getApplicationStatus(app.application_id);
        setApp(updated);
      }, 2000);
    } catch (err) {
      console.error("Resubmit failed:", err);
    } finally {
      setResubmitLoading(false);
    }
  };

  const currentStatus = app?.status || "PENDING";
  const displayStatus = (["DIL_PROCESSING", "AGENTS_RUNNING", "DECIDED_PENDING_OFFICER"].includes(currentStatus))
    ? "PROCESSING"
    : currentStatus === "DATA_REQUIRED"
    ? "DOCUMENTS REQUIRED"
    : currentStatus.replace("OFFICER_", "");

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-24 max-w-3xl">
        <div className="text-center mb-12">
          <h1 className="text-4xl md:text-5xl font-bold font-display text-foreground mb-4 tracking-tight">Track Application</h1>
          <p className="text-muted-foreground text-lg font-light">Enter your application reference ID to check the current status.</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 mb-12">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <Input 
              value={searchId} 
              onChange={(e) => setSearchId(e.target.value)} 
              placeholder="e.g. APP-8273"
              onKeyDown={(e) => e.key === "Enter" && handleSearch()} 
              className="h-14 pl-12 bg-background/50 border-primary/10 transition-all focus:border-primary/40 text-lg" 
            />
          </div>
          <Button onClick={handleSearch} disabled={loading || !searchId} className="h-14 px-8 bg-accent-gradient text-primary-foreground font-bold text-lg shadow-xl hover:scale-105 transition-all">
            {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Track Status"}
          </Button>
        </div>

        {notFound && (
          <div className="bg-destructive/5 text-destructive border border-destructive/20 rounded-2xl p-6 text-center animate-fade-in group">
             <Activity className="h-10 w-10 mx-auto mb-3 opacity-50 group-hover:scale-110 transition-transform" />
             <p className="font-bold text-lg">Application Not Found</p>
             <p className="text-sm opacity-80 mt-1">Unable to locate application "{searchId}". Please check the ID and try again.</p>
          </div>
        )}

        {app && (
          <Card className="shadow-2xl animate-fade-in glass border-primary/5 overflow-hidden">
            <div className="h-2 bg-accent-gradient w-full"></div>
            <CardHeader className="pb-8">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/5 flex items-center justify-center">
                    <CheckCircle2 className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle className="font-display text-2xl">Application Details</CardTitle>
                </div>
                <Badge variant="outline" className={`${statusColors[currentStatus] || "bg-muted"} px-4 py-1.5 rounded-full font-bold uppercase tracking-widest text-xs`}>
                  {displayStatus}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-8">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-8 text-sm">
                <div className="space-y-1">
                  <p className="text-muted-foreground font-medium uppercase tracking-tight text-[10px]">Reference Number</p>
                  <p className="text-xl font-mono font-bold text-foreground">{app.application_id}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground font-medium uppercase tracking-tight text-[10px]">Current Status</p>
                  <p className="text-xl font-bold text-foreground">{displayStatus}</p>
                </div>
              </div>

              {currentStatus === "DATA_REQUIRED" && (
                <div className="bg-warning/5 rounded-2xl p-6 border border-warning/20 relative overflow-hidden">
                  <div className="flex items-start gap-4 mb-4">
                    <div className="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <FileWarning className="h-5 w-5 text-warning" />
                    </div>
                    <div>
                      <h4 className="text-base font-bold text-foreground mb-1">Additional Documents Required</h4>
                      <p className="text-sm text-muted-foreground">
                        Your application is on hold. Please provide the missing information below to resume processing.
                      </p>
                    </div>
                  </div>

                  {/* Missing doc list */}
                  {app.decision?.required_documents && app.decision.required_documents.length > 0 && (
                    <ul className="space-y-2 mb-6">
                      {app.decision.required_documents.map((doc: any, idx: number) => (
                        <li key={idx} className="flex items-start gap-3 bg-background/50 rounded-xl p-3 border border-warning/10">
                          <AlertCircle className="h-4 w-4 text-warning flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-semibold text-foreground">{doc.doc?.replace(/_/g, " ")}</p>
                            {doc.reason && <p className="text-xs text-muted-foreground mt-0.5">{doc.reason}</p>}
                            {doc.impact && <p className="text-xs text-destructive/70 mt-0.5">Impact: {doc.impact}</p>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* Re-upload form */}
                  {resubmitDone ? (
                    <div className="flex items-center gap-2 text-success font-semibold text-sm bg-success/10 rounded-xl p-4 border border-success/20">
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Documents submitted. Pipeline restarted — refreshing status…
                    </div>
                  ) : (
                    <div className="space-y-4 border-t border-warning/10 pt-5">
                      <p className="text-xs font-bold text-foreground uppercase tracking-widest">Upload Missing Documents</p>

                      {/* Income field */}
                      {app.decision?.required_documents?.some((d: any) => d.doc === "INCOME_PROOF") && (
                        <div className="space-y-1">
                          <label className="text-xs text-muted-foreground font-medium">Annual Income (₹)</label>
                          <Input
                            type="number"
                            placeholder="e.g. 840000"
                            value={resubmitIncome}
                            onChange={(e) => setResubmitIncome(e.target.value)}
                            className="h-10 bg-background/70 border-warning/20"
                          />
                        </div>
                      )}

                      {/* Bank statement */}
                      {app.decision?.required_documents?.some((d: any) => d.doc === "BANK_STATEMENT") && (
                        <div className="space-y-1">
                          <label className="text-xs text-muted-foreground font-medium">Bank Statement (PDF / image)</label>
                          <div
                            className="flex items-center gap-3 cursor-pointer bg-background/50 border border-dashed border-warning/30 rounded-xl p-3 hover:border-warning/60 transition-colors"
                            onClick={() => bankRef.current?.click()}
                          >
                            <Upload className="h-4 w-4 text-warning flex-shrink-0" />
                            <span className="text-sm text-muted-foreground">
                              {resubmitFiles.bankStatement ? resubmitFiles.bankStatement.name : "Click to choose file"}
                            </span>
                          </div>
                          <input ref={bankRef} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden"
                            onChange={(e) => setResubmitFiles(f => ({ ...f, bankStatement: e.target.files?.[0] }))} />
                        </div>
                      )}

                      {/* Salary slip */}
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground font-medium">Salary Slip <span className="text-muted-foreground/60">(optional)</span></label>
                        <div
                          className="flex items-center gap-3 cursor-pointer bg-background/50 border border-dashed border-muted/40 rounded-xl p-3 hover:border-warning/40 transition-colors"
                          onClick={() => salaryRef.current?.click()}
                        >
                          <Upload className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <span className="text-sm text-muted-foreground">
                            {resubmitFiles.salarySlip ? resubmitFiles.salarySlip.name : "Click to choose file"}
                          </span>
                        </div>
                        <input ref={salaryRef} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden"
                          onChange={(e) => setResubmitFiles(f => ({ ...f, salarySlip: e.target.files?.[0] }))} />
                      </div>

                      {/* ITR */}
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground font-medium">ITR / Income Tax Return <span className="text-muted-foreground/60">(optional)</span></label>
                        <div
                          className="flex items-center gap-3 cursor-pointer bg-background/50 border border-dashed border-muted/40 rounded-xl p-3 hover:border-warning/40 transition-colors"
                          onClick={() => itrRef.current?.click()}
                        >
                          <Upload className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <span className="text-sm text-muted-foreground">
                            {resubmitFiles.itr ? resubmitFiles.itr.name : "Click to choose file"}
                          </span>
                        </div>
                        <input ref={itrRef} type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden"
                          onChange={(e) => setResubmitFiles(f => ({ ...f, itr: e.target.files?.[0] }))} />
                      </div>

                      <Button
                        onClick={handleResubmit}
                        disabled={resubmitLoading || (!resubmitIncome && !resubmitFiles.bankStatement && !resubmitFiles.salarySlip && !resubmitFiles.itr)}
                        className="w-full h-11 bg-warning text-warning-foreground hover:bg-warning/90 font-bold"
                      >
                        {resubmitLoading
                          ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Uploading…</>
                          : <><Upload className="h-4 w-4 mr-2" />Submit Missing Documents</>}
                      </Button>
                    </div>
                  )}

                  {app.decision?.officer_narrative && (
                    <div className="mt-4 pt-4 border-t border-warning/10">
                      <p className="text-xs text-muted-foreground italic">{app.decision.officer_narrative}</p>
                    </div>
                  )}
                </div>
              )}

              {app.officer_decision && (
                <div className="bg-primary/5 rounded-2xl p-6 border border-primary/10 relative overflow-hidden group">
                  <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <ShieldCheck className="h-16 w-16" />
                  </div>
                  <h4 className="text-lg font-bold text-foreground mb-2 flex items-center gap-2">
                     Application Status
                  </h4>
                  <p className="text-muted-foreground leading-relaxed">
                    {app.officer_decision === "APPROVED" 
                      ? "Your application has been approved. Our team will contact you soon with the next steps." 
                      : app.officer_decision === "REJECTED" 
                        ? "We regret to inform you that your application was not successful at this time." 
                        : "Your application is currently under manual review by our credit officers."}
                  </p>
                  {app.officer_reason && (
                    <div className="mt-4 pt-4 border-t border-primary/10">
                       <p className="text-xs font-bold text-primary mb-1 uppercase tracking-widest">Bank Remarks</p>
                       <p className="text-sm italic text-muted-foreground">"{app.officer_reason}"</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </PublicLayout>
  );
}
