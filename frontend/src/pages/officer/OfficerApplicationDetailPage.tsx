import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, Download, AlertTriangle, CheckCircle2, XCircle, ShieldAlert, BarChart3, Bot, Scale, Briefcase, FileText } from "lucide-react";
import { getFullDecision, submitOfficerAction } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

const statusColors: Record<string, string> = {
  "PENDING": "bg-info/15 text-info border border-info/20",
  "DIL_PROCESSING": "bg-info/15 text-info border border-info/20",
  "AGENTS_RUNNING": "bg-warning/15 text-warning-foreground border border-warning/20",
  "DECIDED_PENDING_OFFICER": "bg-warning/15 text-warning-foreground border border-warning/20",
  "OFFICER_APPROVED": "bg-success/15 text-success border border-success/20",
  "OFFICER_REJECTED": "bg-destructive/15 text-destructive border border-destructive/20",
  "OFFICER_CONDITIONAL": "bg-accent/15 text-accent-foreground border border-accent/20",
  "OFFICER_ESCALATED": "bg-accent/15 text-accent-foreground border border-accent/20",
  "ERROR": "bg-destructive/15 text-destructive border border-destructive/20",
};

export default function OfficerApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [app, setApp] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [decision, setDecision] = useState<string>("APPROVED");
  const [notes, setNotes] = useState("");
  const { toast } = useToast();

  useEffect(() => {
    if (!id) return;

    getFullDecision(id)
      .then((data) => {
        setApp(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch application:", err);
        setLoading(false);
      });
  }, [id]);

  const handleSubmit = async () => {
    if (notes.length < 15) {
      toast({ title: "Error", description: "Please provide at least 15 characters in your notes.", variant: "destructive" });
      return;
    }

    try {
      await submitOfficerAction(id!, {
        officer_id: "admin",
        decision: decision,
        reason: notes,
      });
      toast({ title: "Decision Submitted", description: `Application ${id} marked as ${decision}.` });
      // Refresh the data
      const updatedData = await getFullDecision(id!);
      setApp(updatedData);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to submit decision. Please try again.",
        variant: "destructive",
      });
      console.error("Submission error:", error);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground text-lg">Loading...</p>
      </div>
    );
  }

  if (!app) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground text-lg">Application not found.</p>
        <Button asChild variant="outline" className="mt-4"><Link to="/officer/applications"><ArrowLeft className="mr-2 h-4 w-4" /> Back</Link></Button>
      </div>
    );
  }

  // Backend returns { application: {...}, status: "...", decision: {...}, audit_log: [...] }
  const appData = app.application || {};
  const formData = appData.form_data || appData;
  const aiDecision = app.decision || {};
  const ai = aiDecision.credit_risk || {};
  const fraud = aiDecision.fraud || {};
  const compliance = aiDecision.compliance || {};
  const portfolio = aiDecision.portfolio || {};

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link to="/officer/applications" className="text-muted-foreground hover:text-foreground">Applications</Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-foreground font-medium">{formData.application_id || id}</span>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold font-display text-foreground">{formData.applicant_name || "Application Details"}</h1>
          <p className="text-muted-foreground">Application {formData.application_id || id}</p>
        </div>
        <Badge className={`${statusColors[app.status] || "bg-muted"} text-sm px-3 py-1`}>{app.status}</Badge>
      </div>

      {/* AI Recommendation Banner */}
      {aiDecision.ai_recommendation && (
        <Card className={`border-2 ${aiDecision.ai_recommendation === "REJECT" ? "border-destructive/30 bg-destructive/5" : aiDecision.ai_recommendation === "APPROVE" ? "border-success/30 bg-success/5" : "border-warning/30 bg-warning/5"}`}>
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <Bot className="h-6 w-6 text-foreground" />
                <span className="text-lg font-bold text-foreground">AI Recommendation: {aiDecision.ai_recommendation}</span>
              </div>
              {aiDecision.ai_recommendation === "REJECT" ? <XCircle className="h-8 w-8 text-destructive" /> : aiDecision.ai_recommendation === "APPROVE" ? <CheckCircle2 className="h-8 w-8 text-success" /> : <AlertTriangle className="h-8 w-8 text-warning" />}
            </div>
            <div className={`rounded-lg p-4 ${aiDecision.ai_recommendation === "REJECT" ? "bg-destructive/10" : aiDecision.ai_recommendation === "APPROVE" ? "bg-success/10" : "bg-warning/10"}`}>
              <p className="font-semibold text-foreground mb-1">Officer Summary</p>
              <p className="text-sm text-muted-foreground">{aiDecision.officer_summary || "No summary available"}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI Metrics */}
      {Object.keys(ai).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: "Credit Risk Band", value: ai.risk_band || "N/A", badge: true, color: ai.risk_band === "VERY_HIGH" ? "bg-destructive/15 text-destructive" : ai.risk_band === "LOW" ? "bg-success/15 text-success" : "bg-warning/15 text-warning-foreground" },
            { label: "Credit Score", value: ai.credit_score ? `${(ai.credit_score * 100).toFixed(1)}%` : "N/A" },
            { label: "FOIR", value: ai.foir ? `${ai.foir.toFixed(1)}%` : "N/A" },
            { label: "Fraud Level", value: fraud?.fraud_level || "N/A", badge: true, color: "bg-success/15 text-success" },
            { label: "Compliance", value: compliance?.overall_status || "N/A", badge: true, color: compliance?.overall_status === "PASS" ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive" },
            { label: "DTI Ratio", value: ai.dti_ratio ? `${ai.dti_ratio.toFixed(1)}%` : "N/A" },
          ].map((m) => (
            <Card key={m.label} className="shadow-card">
              <CardContent className="p-4 text-center">
                {m.badge ? <Badge className={`${m.color} mb-1`}>{m.value}</Badge> : <p className="text-2xl font-bold text-foreground">{m.value}</p>}
                <p className="text-xs text-muted-foreground mt-1">{m.label}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Agent Cards */}
      {(Object.keys(ai).length > 0 || Object.keys(fraud).length > 0 || Object.keys(compliance).length > 0 || Object.keys(portfolio).length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.keys(ai).length > 0 && (
            <Card className="shadow-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Credit Risk Agent</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">{ai.officer_narrative || ai.customer_narrative || "Credit risk assessment"}</p>
                <InfoRow label="Risk Score" value={ai.model_risk_score ? `${ai.model_risk_score.toFixed(2)}` : "N/A"} />
                <InfoRow label="Risk Band" value={ai.risk_band || "N/A"} />
                <InfoRow label="Proposed EMI" value={ai.proposed_emi ? `₹${ai.proposed_emi.toLocaleString()}` : "N/A"} />
                <InfoRow label="Surplus/mo" value={ai.net_monthly_surplus ? `₹${ai.net_monthly_surplus.toLocaleString()}` : "N/A"} />
                <InfoRow label="LTV" value={ai.ltv_ratio ? `${ai.ltv_ratio.toFixed(1)}%` : "N/A"} />
              </CardContent>
            </Card>
          )}

          {Object.keys(fraud).length > 0 && (
            <Card className="shadow-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Fraud Agent</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <InfoRow label="Fraud Probability" value={`${(fraud.fraud_probability || 0).toFixed(1)}%`} />
                <InfoRow label="Fraud Level" value={fraud.fraud_level || "CLEAN"} />
                {fraud.fired_soft_signals && fraud.fired_soft_signals.length > 0 && (
                  <div className="bg-warning/10 rounded-lg p-3 mt-2">
                    <p className="font-semibold text-foreground text-xs mb-1">Soft Signals:</p>
                    {fraud.fired_soft_signals.map((s: string, i: number) => <p key={i} className="text-xs text-muted-foreground">• {s}</p>)}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {Object.keys(compliance).length > 0 && (
            <Card className="shadow-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2"><Scale className="h-4 w-4" /> Compliance Agent</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">
                {compliance.block_flags && compliance.block_flags.length > 0 ? (
                  compliance.block_flags.map((f: any, i: number) => (
                    <div key={i} className="bg-destructive/10 rounded-lg p-3 mb-2 text-destructive text-sm">{f.description || f.message}</div>
                  ))
                ) : (
                  <p className="text-success">All compliance checks passed.</p>
                )}
              </CardContent>
            </Card>
          )}

          {Object.keys(portfolio).length > 0 && (
            <Card className="shadow-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2"><Briefcase className="h-4 w-4" /> Portfolio Agent</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">Portfolio recommendation: {portfolio.portfolio_recommendation || "N/A"}</p>
                <InfoRow label="Sector (current)" value={`${(portfolio.sector_concentration_current || 0).toFixed(1)}%`} />
                <InfoRow label="Sector (new)" value={`${(portfolio.sector_concentration_new || 0).toFixed(1)}%`} />
                <InfoRow label="Geo (new)" value={`${(portfolio.geo_concentration_new || 0).toFixed(1)}%`} />
                <InfoRow label="Similar NPA rate" value={`${(portfolio.similar_cases_npa_rate || 0).toFixed(1)}%`} />
                <InfoRow label="EL Impact" value={`₹${(portfolio.el_impact_inr || 0).toLocaleString()}`} />
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Raw Application Data */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="shadow-card">
          <CardHeader className="pb-3"><CardTitle className="text-base">Application Information</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <InfoRow label="Application ID" value={formData.application_id || id || "N/A"} />
            <InfoRow label="Applicant Name" value={formData.applicant_name || "N/A"} />
            <InfoRow label="PAN Number" value={formData.pan_number || "N/A"} />
            <InfoRow label="Email" value={formData.email || "N/A"} />
            <InfoRow label="Mobile" value={formData.mobile_number || "N/A"} />
            <InfoRow label="Status" value={app.status || "N/A"} />
            <InfoRow label="Created" value={appData.created_at ? new Date(appData.created_at).toLocaleString("en-IN") : "N/A"} />
          </CardContent>
        </Card>

        <Card className="shadow-card">
          <CardHeader className="pb-3"><CardTitle className="text-base">Loan Details</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <InfoRow label="Loan Amount" value={formData.loan_amount_requested ? `₹${formData.loan_amount_requested.toLocaleString()}` : "N/A"} />
            <InfoRow label="Loan Tenure" value={formData.loan_tenure_months ? `${formData.loan_tenure_months} months` : "N/A"} />
            <InfoRow label="Loan Purpose" value={formData.loan_purpose || "N/A"} />
            <InfoRow label="Annual Income" value={formData.annual_income ? `₹${formData.annual_income.toLocaleString()}` : "N/A"} />
            <InfoRow label="Employment Type" value={formData.employment_type || "N/A"} />
            <InfoRow label="Employer" value={formData.employer_name || "N/A"} />
          </CardContent>
        </Card>
      </div>

      {/* Officer Action */}
      <Card className="shadow-card border-2 border-border">
        <CardHeader><CardTitle className="font-display">Officer Action</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Decision</Label>
            <Select value={decision} onValueChange={(v) => setDecision(v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="APPROVED">Approve</SelectItem>
                <SelectItem value="REJECTED">Reject</SelectItem>
                <SelectItem value="ESCALATED">Escalate</SelectItem>
                <SelectItem value="CONDITIONAL">Conditional</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Reason / Notes *</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Provide reason for your decision (min 15 characters)" rows={4} />
          </div>
          <div className="flex gap-3">
            <Button onClick={handleSubmit} className="bg-success text-success-foreground hover:bg-success/90">Submit Decision</Button>
            <Button asChild variant="outline"><Link to="/officer/applications"><ArrowLeft className="mr-2 h-4 w-4" /> Back to Queue</Link></Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground font-medium text-right max-w-[65%]">{value}</span>
    </div>
  );
}
