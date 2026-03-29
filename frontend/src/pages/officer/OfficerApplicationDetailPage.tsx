import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { 
  ArrowLeft, AlertTriangle, CheckCircle2, XCircle, ShieldAlert, 
  BarChart3, Bot, Scale, Briefcase, RefreshCw, FileText, 
  ShieldCheck, Activity 
} from "lucide-react";
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
  const [isAuditExpanded, setIsAuditExpanded] = useState(false);
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

  const isPrecheckRejected = aiDecision.decision_matrix_row === "R0_PRECHECK_IDENTITY_MISMATCH" || app.status === "VERIFICATION_FAILED";

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl pb-10">
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
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-3xl font-black font-display text-foreground tracking-tight uppercase">{formData.applicant_name || "Applicant Details"}</h1>
            <Badge variant="outline" className="text-[10px] font-bold border-primary/30 text-primary bg-primary/5 uppercase tracking-tighter shadow-sm">Verified Profile</Badge>
          </div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-[0.2em] font-bold flex items-center gap-2 opacity-80">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-40"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary shadow-[0_0_8px_hsl(var(--primary))]"></span>
            </span>
            ARIA AI Deep Risk Intelligence Active
          </p>
          <p className="text-[10px] text-muted-foreground flex items-center gap-2 mt-3 font-mono opacity-60">
            <span>REFERENCE: {id}</span>
            <span>•</span>
            <span className="lowercase">{formData.email}</span>
          </p>
        </div>
      </div>

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

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <AgentStatCard 
          title="Credit Risk" 
          value={isPrecheckRejected ? "Blocked" : (ai.risk_band ? ai.risk_band : "Wait...")} 
          icon={BarChart3} 
          color={(ai.risk_band === "VERY_HIGH" || ai.risk_band === "HIGH") ? "text-destructive" : (ai.risk_band === "MODERATE" ? "text-warning" : "text-success")} 
        />
        <AgentStatCard 
          title="Fraud Risk" 
          value={isPrecheckRejected ? "Rejected" : (fraud.fraud_probability !== undefined ? `${(fraud.fraud_probability * 100).toFixed(1)}%` : "Wait...")} 
          icon={ShieldAlert} 
          color={fraud.fraud_level === "HIGH_RISK" || isPrecheckRejected ? "text-destructive" : "text-success"} 
        />
        <AgentStatCard 
          title="Compliance" 
          value={isPrecheckRejected ? "Fail" : (compliance.overall_status || "Wait...")} 
          icon={Scale} 
          color={compliance.rbi_compliant ? "text-success" : "text-destructive"} 
        />
        <AgentStatCard 
          title="Portfolio EL" 
          value={isPrecheckRejected ? "Skipped" : (portfolio.el_impact_inr !== undefined ? `₹${(portfolio.el_impact_inr / 1000).toFixed(1)}k` : "Wait...")} 
          icon={Briefcase} 
          color="text-primary" 
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <AgentSection title="Applicant Profile Summary" icon={FileText}>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-y-4 gap-x-6">
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Loan Amount</p>
                <p className="font-semibold text-lg text-primary">₹{form.loan_amount_requested?.toLocaleString() || "0"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Category</p>
                <p className="font-semibold uppercase">{form.loan_category || "PERSONAL"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Purpose</p>
                <p className="font-semibold truncate" title={form.loan_purpose}>{form.loan_purpose || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Tenure</p>
                <p className="font-semibold">{form.loan_tenure_months || 0} Months</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Annual Income</p>
                <p className="font-semibold">₹{form.annual_income?.toLocaleString() || "0"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Gender</p>
                <p className="font-semibold uppercase">{form.gender || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Employer</p>
                <p className="font-semibold truncate">{form.employer_name || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Job Status</p>
                <p className="font-semibold uppercase">{form.employment_type || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Exp.</p>
                <p className="font-semibold">{form.employment_tenure_years || 0} yrs</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Existing EMI</p>
                <p className="font-semibold">₹{form.existing_emi_monthly?.toLocaleString() || "0"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">Asset Value</p>
                <p className="font-semibold">₹{form.residential_assets_value?.toLocaleString() || "0"}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-muted-foreground uppercase">DOB</p>
                <p className="font-semibold">{form.date_of_birth || "—"}</p>
              </div>
            </div>
          </AgentSection>
        </div>
      </div>

      <AgentSection title="Comprehensive Verification Intelligence" icon={ShieldCheck}>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-[160px]">
          {/* Identity Documents */}
          <div className="lg:col-span-1 border-r border-dashed pr-6 space-y-3">
             <p className="text-[10px] font-bold text-muted-foreground uppercase opacity-70 mb-2">Identity Documents</p>
             <DocumentStatus label="PAN Card" status={features.kyc_pan_present ? "VERIFIED" : "MISSING"} />
             <DocumentStatus label="Aadhaar Card" status={features.kyc_aadhaar_present ? "VERIFIED" : "MISSING"} />
          </div>

          {/* Bureau & Network Intelligence */}
          <div className="lg:col-span-3 space-y-4">
            {!isPrecheckRejected && (
              <>
                <div className="grid grid-cols-4 gap-4">
                  <div className="col-span-1 p-2 border rounded bg-muted/10">
                    <p className="text-[9px] font-bold text-muted-foreground uppercase">Bureau Score</p>
                    <p className="text-xl font-bold tracking-tight text-foreground">{features.cibil_score || "—"}</p>
                    <p className="text-[9px] text-muted-foreground font-medium uppercase tracking-tighter opacity-70">CIBIL Mock</p>
                  </div>
                  <div className="col-span-1 p-2 border rounded bg-muted/10">
                    <p className="text-[9px] font-bold text-muted-foreground uppercase">Bureau Age</p>
                    <p className="text-base font-bold text-primary">{features.oldest_account_age_years || "—"} <span className="text-[10px] text-muted-foreground">yrs</span></p>
                    <p className="text-[9px] text-muted-foreground font-medium uppercase tracking-tighter opacity-70">History</p>
                  </div>
                  <div className="col-span-2 grid grid-cols-2 gap-2">
                    <div className="p-2 border rounded bg-muted/10">
                      <p className="text-[9px] font-bold text-muted-foreground uppercase">Util.</p>
                      <p className="text-sm font-bold text-foreground">{((features.credit_utilization_pct || 0) * 100).toFixed(0)}%</p>
                    </div>
                    <div className="p-2 border rounded bg-muted/10">
                      <p className="text-[9px] font-bold text-muted-foreground uppercase">Act. TL %</p>
                      <p className="text-sm font-bold text-foreground">{(features.total_trade_lines > 0) ? ((features.active_tl_pct || 0) * 100).toFixed(0) + "%" : "0%"}</p>
                    </div>
                    <div className="p-2 border rounded bg-muted/10">
                      <p className="text-[9px] font-bold text-muted-foreground uppercase">Delinquencies</p>
                      <p className="text-sm font-bold text-foreground">{features.total_delinquencies || 0}</p>
                    </div>
                    <div className="p-2 border rounded bg-muted/10">
                      <p className="text-[9px] font-bold text-muted-foreground uppercase">Recent Enquiry</p>
                      <p className="text-[10px] font-bold uppercase truncate">{features.recent_enq_product || "NONE"}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-4 border-t border-muted/20">
                   <div className="flex gap-8">
                      <div>
                         <p className="text-[9px] font-bold text-muted-foreground uppercase">Ext. Total Debt</p>
                         <p className="text-sm font-bold font-mono">₹{features.total_outstanding_debt?.toLocaleString() || "0"}</p>
                      </div>
                      <div>
                         <p className="text-[9px] font-bold text-muted-foreground uppercase">Enquiries (6M)</p>
                         <p className="text-sm font-bold">{features.num_hard_enquiries_6m || 0}</p>
                      </div>
                   </div>
                   <div className="flex gap-4 items-center bg-muted/20 px-3 py-1.5 rounded text-[8px] font-mono text-muted-foreground ml-auto">
                      <div className="flex gap-4">
                        <span>IP RISK: {features.ip_risk_score}</span>
                        <span>GEO: {features.ip_country_mismatch ? "LOGGED" : "NATIVE"}</span>
                      </div>
                      {/* <span className="border-l border-muted-foreground/30 pl-3">SID: {appData.application_id?.split('-')[1]}</span> */}
                   </div>
                </div>
              </>
            )}
          </div>
        </div>
      </AgentSection>

      {!isPrecheckRejected && (
        <div className="space-y-4">
          <AgentSection title="1. CREDIT RISK SPECIALIST REPORT" icon={BarChart3}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Model Assessment</p>
                  <div className="flex items-baseline gap-2">
                    <span className={`text-xl font-bold ${(ai.risk_band === "VERY_HIGH" || ai.risk_band === "HIGH") ? "text-destructive" : "text-foreground"}`}>{ai.risk_band}</span>
                    <span className="px-2 py-0.5 rounded-full bg-primary/5 text-primary/70 font-semibold text-[10px] border border-primary/10">
                      Credit Risk Score: {ai.credit_score !== undefined ? `${(ai.credit_score * 100).toFixed(1)}%` : "—"}
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-2 border rounded-sm bg-muted/5">
                    <p className="text-[9px] font-bold text-muted-foreground uppercase">Obligation-to-Income (FOIR)</p>
                    <p className="text-base font-bold text-primary">{features.foir !== undefined ? `${(features.foir * 100).toFixed(1)}%` : "—"}</p>
                  </div>
                  <div className="p-2 border rounded-sm bg-muted/5">
                    <p className="text-[9px] font-bold text-muted-foreground uppercase">Monthly Surplus</p>
                    <p className="text-base font-bold text-success">₹{(ai.credit_agent?.surplusPerMonth || 0).toLocaleString()}</p>
                  </div>
                  <div className="p-2 border rounded-sm bg-muted/5 col-span-2">
                    <p className="text-[9px] font-bold text-muted-foreground uppercase">Proposed Monthly EMI</p>
                    <p className="text-base font-bold text-foreground">₹{(ai.credit_agent?.proposedEMI || 0).toLocaleString()}</p>
                  </div>
                </div>
              </div>

              <div className="md:col-span-2 border-l pl-6">
                <p className="text-[10px] font-bold text-muted-foreground uppercase mb-3 text-slate-400">Risk Contribution Factors</p>
                <div className="flex flex-wrap gap-2 mb-4">
                  {(ai.shap_top_features || []).map((f: string) => (
                    <span key={f} className="px-2 py-1 bg-muted/10 text-muted-foreground border border-muted-foreground/10 rounded text-[10px] font-medium">
                      {f}
                    </span>
                  ))}
                </div>
                <ProcessCheck label="Loan-to-Value (LTV)" value={appData.form_data?.residential_assets_value ? ((appData.form_data?.loan_amount_requested / appData.form_data?.residential_assets_value) * 100).toFixed(1) + "%" : "UNSECURED"} status="PASS" />
                <div className="mt-4">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Underwriting Narrative</p>
                  <p className="text-sm text-foreground/80 leading-normal">{ai.officer_narrative || "No narrative available."}</p>
                </div>
              </div>
            </div>
          </AgentSection>

          <AgentSection title="2. FRAUD DETECTION & VERIFICATION" icon={ShieldAlert}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Fraud Probability</p>
                  <p className={`text-xl font-bold ${fraud.fraud_level === "HIGH_RISK" ? "text-destructive" : "text-foreground"}`}>
                    {fraud.fraud_probability !== undefined ? `${(fraud.fraud_probability * 100).toFixed(1)}%` : "0.0%"}
                  </p>
                </div>
                <div className="space-y-3">
                  <ProcessCheck label="Identity Match" value={fraud.identity_consistency || "Wait..."} status={fraud.identity_consistency === "HIGH" ? "PASS" : "WARN"} />
                  {fraud.recommend_kyc_recheck && (
                    <div className="flex items-center gap-1.5 px-2 py-1 bg-destructive/5 border border-destructive/20 rounded-sm text-destructive animate-pulse">
                      <ShieldAlert className="h-3 w-3" />
                      <span className="text-[10px] font-bold uppercase tracking-tighter">KYC RECHECK REQ</span>
                    </div>
                  )}
                  <div>
                    <p className="text-[9px] font-bold text-muted-foreground uppercase mb-1">Triggered Signals</p>
                    <div className="flex flex-wrap gap-1">
                      {([...(fraud.fired_hard_rules || []), ...(fraud.fired_soft_signals || [])]).length > 0 ? (
                        ([...(fraud.fired_hard_rules || []), ...(fraud.fired_soft_signals || [])]).map((r: any, i: number) => (
                          <span key={i} className="px-1.5 py-0.5 bg-muted/20 text-[9px] font-medium rounded border border-muted-foreground/10 flex items-center gap-1">
                            {r.includes("HARD") ? <XCircle className="h-2 w-2 text-destructive" /> : <AlertTriangle className="h-2 w-2 text-yellow-500" />}
                            {r}
                          </span>
                        ))
                      ) : (
                        <span className="text-[10px] text-muted-foreground italic font-medium">No signals hit</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              <div className="md:col-span-2 border-l pl-6">
                <p className="text-sm text-foreground/80 leading-normal mb-8">{fraud.explanation || "No suspicious patterns detected."}</p>
                <div className="pt-2 border-t border-muted/20">
                   <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">IP Fingerprint Risk</p>
                   <div className="flex items-center gap-2">
                      <div className="h-1.5 w-full bg-muted/20 rounded-full overflow-hidden max-w-[120px]">
                         <div className="h-full bg-primary/40 rounded-full" style={{ width: `${(fraud.ip_risk_score || 0) * 100}%` }} />
                      </div>
                      <span className="text-[10px] font-semibold text-muted-foreground">{((fraud.ip_risk_score || 0) * 100).toFixed(0)}%</span>
                   </div>
                </div>
              </div>
            </div>
          </AgentSection>

          <AgentSection title="3. REGULATORY COMPLIANCE AUDIT" icon={Scale}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Overall Compliance</p>
                  <p className="text-xl font-bold">{compliance.overall_status || "PENDING"}</p>
                </div>
                <div className="space-y-2 pb-2">
                  <ProcessCheck label="RBI Master Circular" value={compliance.rbi_compliant ? "PASS" : "FAIL"} status={compliance.rbi_compliant ? "PASS" : "FAIL"} />
                  <ProcessCheck label="AML Screening" value={compliance.aml_review_required ? "REVIEW" : "CLEAN"} status={compliance.aml_review_required ? "WARN" : "PASS"} />
                  <ProcessCheck label="KYC Verification" value={compliance.kyc_complete ? "VERIFIED" : "PENDING"} status={compliance.kyc_complete ? "PASS" : "WARN"} />
                </div>
                {compliance.block_flags?.length > 0 && (
                   <div className="pt-2 border-t border-muted/20">
                      <p className="text-[9px] font-bold text-destructive uppercase mb-1">Regulation Flags</p>
                      {compliance.block_flags.map((f: any, i: number) => (
                         <div key={i} className="text-[10px] text-destructive truncate flex items-center gap-1 font-medium italic"><XCircle className="h-2 w-2" /> {f.rule_id || f}</div>
                      ))}
                   </div>
                )}
              </div>
              <div className="md:col-span-2 border-l pl-6 text-sm text-foreground/80 leading-normal">
                {compliance.narrative || "Compliance check completed."}
              </div>
            </div>
          </AgentSection>

          <AgentSection title="4. PORTFOLIO EXPOSURE ANALYSIS" icon={Briefcase}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">Exposure Impact</p>
                  <p className="text-xl font-bold tracking-tight">{(portfolio.el_impact_inr || 0).toLocaleString()} INR</p>
                </div>
                <div className="space-y-2">
                  <ProcessCheck label="Sector Exposure" value={(portfolio.sector_concentration_new * 100).toFixed(2) + "%"} status={portfolio.concentration_flags?.includes("SECTOR_CONCENTRATION_BREACH") ? "FAIL" : "PASS"} />
                  <ProcessCheck label="Geography Exposure" value={(portfolio.geo_concentration_new * 100).toFixed(2) + "%"} status="PASS" />
                </div>
                {portfolio.concentration_flags?.length > 0 && (
                   <div className="pt-2 border-t border-muted/20">
                      <p className="text-[9px] font-bold text-muted-foreground uppercase mb-1">Concentration Signals</p>
                      <div className="flex flex-wrap gap-1">
                         {portfolio.concentration_flags.map((flag: string) => (
                            <span key={flag} className="px-1 py-0.5 bg-muted/20 text-[9px] text-muted-foreground font-semibold rounded border border-muted-foreground/10">{flag}</span>
                         ))}
                      </div>
                   </div>
                )}
              </div>
              <div className="md:col-span-2 border-l pl-6">
                <p className="text-sm text-foreground/80 leading-normal mb-8 italic">{portfolio.cot_reasoning || "Exposure within risk limits."}</p>
                {portfolio.el_impact_note && (
                   <div className="p-3 bg-muted/10 border border-muted/20 rounded-md">
                      <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1">EL Impact Note</p>
                      <p className="text-xs text-muted-foreground italic font-medium">"{portfolio.el_impact_note}"</p>
                   </div>
                )}
              </div>
            </div>
          </AgentSection>
          <AgentSection 
            title="5. COMPREHENSIVE AUDIT TRAIL & TRANSMISSION EVENTS" 
            icon={Activity}
            action={
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => setIsAuditExpanded(!isAuditExpanded)}
                className="h-6 px-2 text-[10px] font-bold text-muted-foreground hover:text-primary transition-colors"
              >
                {isAuditExpanded ? "COLLAPSE HISTORY" : "EXPAND AUDIT LOG"}
              </Button>
            }
          >
            {isAuditExpanded ? (
              <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                <div className="border rounded-lg bg-muted/10 overflow-hidden">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-muted/50 text-[10px] font-bold uppercase tracking-widest text-muted-foreground border-b border-muted">
                        <th className="px-4 py-2 w-1/4">Timestamp</th>
                        <th className="px-4 py-2 w-1/6">Level</th>
                        <th className="px-4 py-2 w-1/4">Event Source</th>
                        <th className="px-4 py-2">Details / Narrative</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-muted/30">
                      {(app.audit_log || []).slice().reverse().map((event: any, i: number) => {
                        const isOfficer = (event.agent_name || "").toLowerCase() === "officer";
                        const isSystem = (event.agent_name || "").toLowerCase() === "system";
                        const isBot = !isOfficer && !isSystem;
                        return (
                          <tr key={i} className={`text-[11px] hover:bg-muted/5 transition-colors ${isOfficer ? "bg-primary/5 font-medium" : ""}`}>
                            <td className="px-4 py-2 text-muted-foreground font-mono">
                              {new Date(event.created_at || event.timestamp).toLocaleString(undefined, { 
                                hour: '2-digit', 
                                minute: '2-digit', 
                                second: '2-digit',
                                day: '2-digit',
                                month: 'short'
                              })}
                            </td>
                            <td className="px-4 py-2">
                              <Badge variant="outline" className={`text-[9px] py-0 h-4 uppercase ${
                                event.event_type === "ERROR" ? "text-destructive border-destructive/30" : 
                                event.event_type === "OFFICER_ACTION" ? "text-primary border-primary/30" : "text-muted-foreground"
                              }`}>
                                {(event.event_type || event.event_name || "EVENT").replace("_", " ")}
                              </Badge>
                            </td>
                            <td className="px-4 py-2 flex items-center gap-2">
                              {isOfficer ? <ShieldCheck className="h-3 w-3 text-primary" /> : isSystem ? <ShieldCheck className="h-3 w-3 text-muted-foreground" /> : <Bot className="h-3 w-3 text-primary" />}
                              <span className="capitalize">{event.agent_name || "System"}</span>
                            </td>
                            <td className="px-4 py-2 max-w-lg truncate" title={JSON.stringify(event.payload)}>
                              <p className="text-foreground/90 leading-relaxed font-light">
                                {event.payload?.reason || event.payload?.message || (typeof event.payload === 'string' ? event.payload : "View Payload Data")}
                              </p>
                            </td>
                          </tr>
                        );
                      })}
                      {(app.audit_log || []).length === 0 && (
                        <tr>
                          <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground italic tracking-tight">No audit events recorded for this vector.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="flex justify-between items-center text-[10px] text-muted-foreground px-2">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-primary/20" /> OFFICER ACTION</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-muted/40" /> SYSTEM / AGENT EVENT</span>
                  </div>
                  <p className="font-mono">SID: {id}</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-8 gap-3 border border-dashed rounded-lg bg-muted/5 opacity-70">
                 <Activity className="h-8 w-8 text-muted-foreground/30" />
                 <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">Transmission Log Secreted</p>
                 <Button variant="outline" size="sm" onClick={() => setIsAuditExpanded(true)} className="h-8 text-[10px] font-bold">REVEAL LOGS</Button>
              </div>
            )}
          </AgentSection>
        </div>
      )}

      {!app.status.startsWith("OFFICER_") && (
        <Card className="shadow-none border border-border">
          <CardHeader className="pb-3 px-4">
            <CardTitle className="text-lg font-bold">Officer Final Action</CardTitle>
            <CardDescription className="text-xs">Submit the final processing decision for this application.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="md:col-span-1 space-y-3">
                <Label className="text-xs font-bold uppercase tracking-wider">Select Decision</Label>
                <div className="grid grid-cols-1 gap-2">
                  {["APPROVED", "REJECTED", "ESCALATED", "CONDITIONAL"].map((d) => (
                    <Button 
                      key={d} 
                      variant={decision === d ? "default" : "outline"} 
                      onClick={() => setDecision(d)}
                      className={`justify-start h-10 text-xs font-bold ${decision === d ? (d === "REJECTED" ? "bg-destructive hover:bg-destructive" : "bg-primary hover:bg-primary") : ""}`}
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
                  placeholder="Enter detailed reasoning..." 
                  className="min-h-[140px] text-sm bg-background border-border" 
                />
                <div className="flex items-center justify-between">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">Audit logs will reflect this action.</p>
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

function AgentSection({ title, icon: Icon, action, children }: any) {
  return (
    <div className="border rounded-md overflow-hidden bg-card">
      <div className="bg-muted/30 py-2 px-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{title}</h4>
        </div>
        {action}
      </div>
      <div className="p-4">
        {children}
      </div>
    </div>
  );
}
