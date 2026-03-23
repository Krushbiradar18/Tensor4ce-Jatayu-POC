import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, AlertTriangle, CheckCircle2, XCircle, ShieldAlert, BarChart3, Bot, Scale, Briefcase, RefreshCw, FileText, Info, ShieldCheck, Activity, FileCheck, Search, TrendingUp, TrendingDown } from "lucide-react";
import { getFullDecision, submitOfficerAction } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useQuery } from "@tanstack/react-query";

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
  const [decision, setDecision] = useState<string>("APPROVED");
  const [notes, setNotes] = useState("");
  const { toast } = useToast();

  const isFinalStatus = (status: string) => 
    status?.startsWith("OFFICER_") || status === "ERROR" || status === "VERIFICATION_FAILED";

  const { data: app, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["application", id],
    queryFn: () => getFullDecision(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !isFinalStatus(status) ? 5000 : false;
    },
  });

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
      refetch();
    } catch (error) {
      toast({ title: "Error", description: "Failed to submit decision.", variant: "destructive" });
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in max-w-5xl">
        <div className="h-6 w-32 bg-muted rounded animate-pulse" />
        <div className="h-10 w-full bg-muted rounded animate-pulse" />
        <div className="h-64 w-full bg-muted rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="h-48 bg-muted rounded animate-pulse" />
          <div className="h-48 bg-muted rounded animate-pulse" />
        </div>
      </div>
    );
  }

  if (!app) {
    return (
      <div className="text-center py-20 bg-muted/20 border border-dashed rounded-xl">
        <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4"><FileText className="h-8 w-8 text-muted-foreground" /></div>
        <p className="text-muted-foreground text-lg font-medium">Application not found.</p>
        <Button asChild variant="outline" className="mt-4 shadow-sm"><Link to="/officer/applications"><ArrowLeft className="mr-2 h-4 w-4" /> Go to Queue</Link></Button>
      </div>
    );
  }

  const appData = app.application || {};
  const formData = appData.form_data || appData;
  const aiDecision = app.decision || {};
  const ai = aiDecision.credit_risk || {};
  const fraud = aiDecision.fraud || {};
  const compliance = aiDecision.compliance || {};
  const portfolio = aiDecision.portfolio || {};
  const ctx = aiDecision.context || {};
  const features = ctx.features || {};
  const form = ctx.form || formData;

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl pb-10">
      {/* Breadcrumb & Status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <Link to="/officer/applications" className="text-muted-foreground hover:text-primary transition-colors">Queue</Link>
          <span className="text-muted-foreground">/</span>
          <span className="text-foreground font-bold font-mono">{id}</span>
        </div>
        <div className="flex items-center gap-3">
          {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-primary" />}
          <Badge className={`${statusColors[app.status] || "bg-muted"} px-3 py-1 shadow-sm`}>{app.status}</Badge>
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold font-sans text-foreground">{formData.applicant_name || "Applicant Details"}</h1>
          <p className="text-sm text-muted-foreground flex items-center gap-2 mt-1">
            <span className="bg-muted px-2 py-0.5 rounded text-[10px] font-mono border">{id}</span>
            <span>• {formData.email}</span>
          </p>
        </div>
      </div>

      {/* Top AI Decision - Sober Version */}
      {aiDecision.ai_recommendation && (
        <div className={`p-4 border rounded-md flex items-center justify-between ${
          aiDecision.ai_recommendation === "REJECT" ? "border-l-4 border-l-destructive bg-destructive/5 border-destructive/20" : 
          aiDecision.ai_recommendation === "APPROVE" ? "border-l-4 border-l-success bg-success/5 border-success/20" : 
          "border-l-4 border-l-warning bg-warning/5 border-warning/20"
        }`}>
          <div className="flex items-center gap-3">
            <div className={`${
              aiDecision.ai_recommendation === "REJECT" ? "text-destructive" : 
              aiDecision.ai_recommendation === "APPROVE" ? "text-success" : 
              "text-warning"
            }`}>
              <Bot className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-bold uppercase tracking-tight">AI Assessment Outcome: {aiDecision.ai_recommendation}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] font-bold text-muted-foreground uppercase">Policy Match:</span>
                <Badge variant="outline" className="text-[10px] font-mono py-0 h-4 border-muted-foreground/30">{aiDecision.decision_matrix_row || "SYSTEM_DEFAULT"}</Badge>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* KPI Cards - Agent Summaries */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <AgentStatCard 
          title="Credit Risk" 
          value={ai.risk_band ? `${ai.risk_band} (${ai.model_risk_score || "—"})` : "Wait..."} 
          icon={BarChart3} 
          color={(ai.risk_band === "VERY_HIGH" || ai.risk_band === "HIGH") ? "text-destructive" : (ai.risk_band === "MODERATE" ? "text-warning" : "text-success")} 
        />
        <AgentStatCard 
          title="Fraud Risk" 
          value={fraud.fraud_probability !== undefined ? `${(fraud.fraud_probability * 100).toFixed(1)}%` : "Wait..."} 
          icon={ShieldAlert} 
          color={fraud.fraud_level === "HIGH_RISK" ? "text-destructive" : "text-success"} 
        />
        <AgentStatCard 
          title="Compliance" 
          value={compliance.overall_status || "Wait..."} 
          icon={Scale} 
          color={compliance.rbi_compliant ? "text-success" : "text-destructive"} 
        />
        <AgentStatCard 
          title="Portfolio EL" 
          value={portfolio.el_impact_inr !== undefined ? `₹${(portfolio.el_impact_inr / 1000).toFixed(1)}k` : "Wait..."} 
          icon={Briefcase} 
          color="text-primary" 
        />
      </div>

      {/* Profile and External Data Sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Applicant Profile */}
        <AgentSection title="Applicant Profile & Financials" icon={FileText}>
          <div className="grid grid-cols-2 gap-y-4 gap-x-6 text-sm">
            <div>
              <p className="text-[10px] font-bold text-muted-foreground uppercase">Permanent PAN</p>
              <p className="font-semibold uppercase">{form.pan_number || "—"}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-muted-foreground uppercase">Annual Income</p>
              <p className="font-semibold">₹{form.annual_income?.toLocaleString() || "0"}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-muted-foreground uppercase">Employment</p>
              <p className="font-semibold">{form.employment_type || "—"} ({form.employment_tenure_years || 0} yrs)</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-muted-foreground uppercase">Loan Purpose</p>
              <p className="font-semibold">{form.loan_purpose || "—"}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-muted-foreground uppercase">Existing Obligation</p>
              <p className="font-semibold">₹{form.existing_emi_monthly?.toLocaleString() || "0"} /mo</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-muted-foreground uppercase">Collateral/Assets</p>
              <p className="font-semibold">₹{form.residential_assets_value?.toLocaleString() || "0"}</p>
            </div>
          </div>
        </AgentSection>

        {/* Mock API Verification Data */}
        <AgentSection title="External Verification (Mock APIs)" icon={ShieldCheck}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-2 border rounded bg-muted/20">
                <p className="text-[9px] font-bold text-muted-foreground uppercase">Bureau Score</p>
                <p className="text-base font-bold text-primary">{features.cibil_score || "—"}</p>
                <p className="text-[9px] text-muted-foreground">Source: TransUnion Mock Engine</p>
              </div>
              <div className="p-2 border rounded bg-muted/20">
                <p className="text-[9px] font-bold text-muted-foreground uppercase">Risk Probability</p>
                <p className="text-base font-bold text-primary">{(features.foir * 100).toFixed(1)}% FOIR</p>
                <p className="text-[9px] text-muted-foreground">Policy: Internal Scorecard</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="flex items-center justify-between border-b pb-1">
                <span className="text-muted-foreground uppercase font-bold">IP Risk Score:</span>
                <span className={features.ip_risk_score > 0.5 ? "text-destructive" : "text-success font-bold"}>{features.ip_risk_score || "0.0"}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-1">
                <span className="text-muted-foreground uppercase font-bold">Country Lock:</span>
                <span className={features.ip_country_mismatch ? "text-destructive" : "text-success font-bold"}>{features.ip_country_mismatch ? "FAIL" : "IN"}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-1">
                <span className="text-muted-foreground uppercase font-bold">Outstanding Loans:</span>
                <span className="font-bold">{features.num_active_loans || 0}</span>
              </div>
              <div className="flex items-center justify-between border-b pb-1">
                <span className="text-muted-foreground uppercase font-bold">Enquiries (6m):</span>
                <span className={features.num_hard_enquiries_6m > 3 ? "text-destructive" : "font-bold"}>{features.num_hard_enquiries_6m || 0}</span>
              </div>
            </div>
          </div>
        </AgentSection>
      </div>

      {/* Uploaded Documents Checklist */}
      <AgentSection title="Document & Verification Checklist" icon={Activity}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <DocumentStatus label="PAN Card" status={features.kyc_pan_present ? "VERIFIED" : "MISSING"} />
          <DocumentStatus label="Aadhaar Card" status={features.kyc_aadhaar_present ? "VERIFIED" : "MISSING"} />
          <DocumentStatus label="Bank Statement (6M)" status={features.bank_statement_months >= 6 ? "VERIFIED" : (features.bank_statement_months > 0 ? "PARTIAL" : "MISSING")} />
          <DocumentStatus label="Salary Slip / Form 16" status={features.annual_income_verified > 0 ? "VERIFIED" : "NOT_SUBMITTED"} />
        </div>
      </AgentSection>

      {/* Detailed Agent Result Sections - More Sober */}
      <div className="space-y-4">
        {/* Credit Risk Section */}
        <AgentSection title="1. CREDIT RISK SPECIALIST REPORT" icon={BarChart3}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-4">
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Model Assessment</p>
                <div className="flex items-baseline gap-2">
                  <span className={`text-xl font-bold ${(ai.risk_band === "VERY_HIGH" || ai.risk_band === "HIGH") ? "text-destructive" : "text-foreground"}`}>{ai.risk_band}</span>
                  <span className="text-xs text-muted-foreground">(Score: {ai.model_risk_score}/100)</span>
                </div>
              </div>
              <div className="space-y-2">
                <ProcessCheck label="Prob. of Default (PD)" value={`${(ai.credit_score * 100).toFixed(2)}%`} status={ai.credit_score > 0.5 ? "FAIL" : "PASS"} />
                <ProcessCheck label="Debt Service Coverage" value={`${(ai.foir * 100).toFixed(1)}%`} status={ai.foir > 0.5 ? "FAIL" : "PASS"} />
                <ProcessCheck label="Loan-to-Value (LTV)" value={`${(ai.ltv * 100).toFixed(1)}%`} status="PASS" />
              </div>
            </div>
            <div className="md:col-span-2 border-l pl-6 space-y-4">
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Underwriting Narrative</p>
                <p className="text-sm text-foreground/80 leading-normal">{ai.officer_narrative || "No narrative available."}</p>
              </div>
              {ai.top_factors && ai.top_factors.length > 0 && (
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Risk Contribution Factors (SHAP)</p>
                  <div className="flex flex-wrap gap-2">
                    {ai.top_factors.slice(0, 5).map((f: any, i: number) => (
                      <span key={i} className={`text-[10px] px-2 py-0.5 border rounded-sm flex items-center gap-1 ${f.direction === "NEGATIVE" ? "bg-destructive/5 text-destructive border-destructive/10" : "bg-success/5 text-success border-success/10"}`}>
                        {f.human_label || f.feature} ({(f.shap_value || 0).toFixed(2)})
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </AgentSection>

        {/* Fraud Section */}
        <AgentSection title="2. FRAUD DETECTION & VERIFICATION" icon={ShieldAlert}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-4">
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Fraud Probability</p>
                <p className={`text-xl font-bold ${fraud.fraud_level === "HIGH_RISK" ? "text-destructive" : "text-foreground"}`}>
                  {(fraud.fraud_probability * 100).toFixed(1)}%
                </p>
              </div>
              <div className="space-y-2">
                <ProcessCheck label="Identity Consistency" value={fraud.identity_consistency} status={fraud.identity_consistency === "HIGH" ? "PASS" : "WARN"} />
                <ProcessCheck label="IP Risk Assessment" value={features.ip_risk_score} status={features.ip_risk_score > 0.5 ? "FAIL" : "PASS"} />
                <FormatLabel label="Hard Blocks Triggered" value={fraud.fired_hard_rules?.length || 0} color={fraud.fired_hard_rules?.length > 0 ? "text-destructive" : "text-muted-foreground"} />
              </div>
            </div>
            <div className="md:col-span-2 border-l pl-6">
              <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Detailed Analysis</p>
              <p className="text-sm text-foreground/80 leading-normal mb-4">{fraud.explanation || "No suspicious patterns detected in metadata."}</p>
              
              <div className="grid grid-cols-2 gap-4">
                {fraud.fired_hard_rules?.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[9px] font-bold text-destructive uppercase">Security Violations</p>
                    {fraud.fired_hard_rules.map((r: any, i: number) => (
                      <div key={i} className="text-[10px] flex items-center gap-1 font-medium"><XCircle className="h-3 w-3" /> {r}</div>
                    ))}
                  </div>
                )}
                {fraud.fired_soft_signals?.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[9px] font-bold text-warning-foreground uppercase">Anomaly Signals</p>
                    {fraud.fired_soft_signals.map((s: any, i: number) => (
                      <div key={i} className="text-[10px] flex items-center gap-1 font-medium"><AlertTriangle className="h-3 w-3" /> {s}</div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </AgentSection>

        {/* Compliance Section */}
        <AgentSection title="3. REGULATORY COMPLIANCE AUDIT" icon={Scale}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-4">
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Overall Compliance</p>
                <p className={`text-xl font-bold ${compliance.overall_status === "BLOCK_FAIL" ? "text-destructive" : "text-foreground"}`}>
                  {compliance.overall_status}
                </p>
              </div>
              <div className="space-y-2">
                <ProcessCheck label="RBI Master Circular" value={compliance.rbi_compliant ? "COMPLIANT" : "NON-COMPLIANT"} status={compliance.rbi_compliant ? "PASS" : "FAIL"} />
                <ProcessCheck label="AML/CTF Screening" value={compliance.aml_review_required ? "REVIEW" : "CLEAN"} status={compliance.aml_review_required ? "WARN" : "PASS"} />
                <ProcessCheck label="KYC Sufficiency" value={features.kyc_pan_present && features.kyc_aadhaar_present ? "OK" : "INCOMPLETE"} status={features.kyc_pan_present && features.kyc_aadhaar_present ? "PASS" : "FAIL"} />
              </div>
            </div>
            <div className="md:col-span-2 border-l pl-6">
              <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Audit Trail & Rationale</p>
              <p className="text-sm text-foreground/80 leading-normal mb-4">{compliance.narrative || "System checks validated against standard bank policies."}</p>
              
              {compliance.block_flags?.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[9px] font-bold text-destructive uppercase">Policy Blocks</p>
                  {compliance.block_flags.map((f: any, i: number) => (
                    <div key={i} className="text-[10px] p-2 bg-destructive/5 border border-destructive/10 rounded-sm">
                      <span className="font-bold">{f.rule_id}:</span> {f.description}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </AgentSection>

        {/* Portfolio Section */}
        <AgentSection title="4. PORTFOLIO EXPOSURE ANALYSIS" icon={Briefcase}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-4">
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Concentration Risk</p>
                <p className="text-xl font-bold">{portfolio.portfolio_recommendation}</p>
              </div>
              <div className="p-3 border rounded bg-primary/5">
                <p className="text-[9px] font-bold text-primary uppercase mb-1">Expected Loss (EL)</p>
                <p className="text-base font-bold text-primary tracking-tight">₹{portfolio.el_impact_inr?.toLocaleString() || "0"}</p>
                <p className="text-[9px] text-muted-foreground mt-1 underline decoration-primary/20">Impact on personal loan pool</p>
              </div>
            </div>
            <div className="md:col-span-2 border-l pl-6">
              <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Portfolio Strategy Observation</p>
              <p className="text-sm text-foreground/80 leading-normal mb-4">{portfolio.cot_reasoning || "Exposure remains within limits for this applicant sector."}</p>
              
              <div className="grid grid-cols-2 gap-4 text-[11px]">
                <div className="flex items-center justify-between border-b pb-1">
                  <span className="text-muted-foreground">Sector Concentration:</span>
                  <span className="font-bold">{(portfolio.sector_concentration_new * 100).toFixed(2)}%</span>
                </div>
                <div className="flex items-center justify-between border-b pb-1">
                  <span className="text-muted-foreground">Product Cap:</span>
                  <span className="font-bold text-success">OK</span>
                </div>
              </div>
            </div>
          </div>
        </AgentSection>
      </div>

      {/* Decision Panel */}
      {!app.status.startsWith("OFFICER_") && (
        <Card className="shadow-none border border-border">
          <CardHeader className="pb-3 px-4">
            <CardTitle className="text-lg font-bold font-sans">Officer Final Action</CardTitle>
            <CardDescription className="text-xs">Submit the final processing decision for this application.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="md:col-span-1 space-y-3">
                <Label className="text-xs font-bold text-primary uppercase tracking-wider">Select Decision</Label>
                <div className="grid grid-cols-1 gap-2">
                  {["APPROVED", "REJECTED", "ESCALATED", "CONDITIONAL"].map((d) => (
                    <Button 
                      key={d} 
                      variant={decision === d ? "default" : "outline"} 
                      onClick={() => setDecision(d)}
                      className={`justify-start h-10 text-xs font-bold transition-none ${decision === d ? (d === "REJECTED" ? "bg-destructive hover:bg-destructive" : "bg-primary hover:bg-primary") : ""}`}
                    >
                      {d}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="md:col-span-2 space-y-3">
                <Label className="text-xs font-bold uppercase tracking-wider">Justification Notes *</Label>
                <Textarea 
                  value={notes} 
                  onChange={(e) => setNotes(e.target.value)} 
                  placeholder="Enter detailed reasoning for the final decision..." 
                  className="min-h-[140px] text-sm bg-background border-border resize-none" 
                />
                <div className="flex items-center justify-between">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">Internal review audit will be logged.</p>
                  <Button onClick={handleSubmit} className="px-10 h-10 text-xs font-bold uppercase tracking-widest shadow-none">Submit Decision</Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ProcessCheck({ label, value, status }: { label: string; value: string | number; status: "PASS" | "FAIL" | "WARN" }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-muted/30">
      <span className="text-[10px] text-muted-foreground uppercase font-bold">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-bold">{value}</span>
        {status === "PASS" ? <CheckCircle2 className="h-3 w-3 text-success" /> : 
         status === "FAIL" ? <XCircle className="h-3 w-3 text-destructive" /> : 
         <AlertTriangle className="h-3 w-3 text-warning" />}
      </div>
    </div>
  );
}

function FormatLabel({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-muted/30">
      <span className="text-[10px] text-muted-foreground uppercase font-bold">{label}</span>
      <span className={`text-[11px] font-bold ${color || ""}`}>{value}</span>
    </div>
  );
}

function DocumentStatus({ label, status }: { label: string; status: string }) {
  const isOk = status === "VERIFIED" || status === "SIGNED";
  const isErr = status === "MISSING" || status === "NOT_SUBMITTED" || status === "FAILED";
  
  return (
    <div className="flex items-center justify-between p-2 border rounded bg-muted/5">
      <div className="min-w-0">
        <p className="text-[10px] font-bold text-muted-foreground uppercase truncate">{label}</p>
        <p className={`text-[11px] font-bold ${isOk ? "text-success" : (isErr ? "text-destructive" : "text-warning")}`}>{status}</p>
      </div>
      {isOk ? <CheckCircle2 className="h-4 w-4 text-success" /> : (isErr ? <XCircle className="h-4 w-4 text-destructive" /> : <AlertTriangle className="h-4 w-4 text-warning" />)}
    </div>
  );
}

function AgentStatCard({ title, value, icon: Icon, color }: { title: string; value: string; icon: any; color: string }) {
  return (
    <Card className="shadow-none border-border group hover:border-primary/30 transition-colors bg-card">
      <CardContent className="p-3 flex items-center gap-3">
        <div className={`p-2 rounded-md bg-muted/40 ${color}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest truncate">{title}</p>
          <p className={`text-md font-bold truncate ${value === "Wait..." ? "animate-pulse text-muted-foreground" : "text-foreground"}`}>{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function AgentSection({ title, icon: Icon, children }: any) {
  return (
    <div className="border rounded-md overflow-hidden bg-card">
      <div className="bg-muted/30 py-2 px-4 border-b flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{title}</h4>
      </div>
      <div className="p-4">
        {children}
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-semibold text-foreground text-right max-w-[60%] truncate">{value}</span>
    </div>
  );
}
