import { useState, useCallback, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Check, Upload, X, ArrowLeft, ArrowRight, Save,
  FileText, CreditCard, Building2, Receipt, FileBadge,
  CheckCircle2, AlertCircle, Loader2,
} from "lucide-react";
import { submitApplication as submitApplicationAPI } from "@/lib/api";
import { PersonalInfo, EmploymentInfo, LoanInfo, LoanType, LoanTerm, UploadedDoc } from "@/lib/types";
import { useToast } from "@/hooks/use-toast";

const steps = ["Personal Info", "Employment", "Loan Details", "Review & Submit"];
const loanTypes: LoanType[] = ["Personal"];
const loanTerms: LoanTerm[] = [12, 24, 36, 48, 60];
const indianStates = ["Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","Delhi","Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka","Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura","Uttar Pradesh","Uttarakhand","West Bengal"];

const initialPersonal: PersonalInfo = { fullName:"",dateOfBirth:"",aadhaarNumber:"",panNumber:"",email:"",phone:"",address:"",city:"",state:"",pinCode:"" };
const initialEmployment: EmploymentInfo = { employmentStatus:"",employerName:"",jobTitle:"",monthlyIncome:0,yearsAtJob:0,additionalIncome:"" };
const initialLoan: LoanInfo = { loanType:"Personal",loanAmount:0,loanPurpose:"",loanTerm:12,existingDebts:"" };

type DocKey = "aadhaar" | "pan" | "bank_statement" | "salary_slip";
type DocUploadStatus = "idle" | "uploading" | "done" | "error";
interface DocUploadState { file: File | null; status: DocUploadStatus; result: Record<string, unknown> | null; error: string | null; }

const DOC_SLOTS = [
  { key: "pan" as DocKey, label: "PAN Card", icon: FileBadge, required: true, accept: ".pdf,.jpg,.jpeg,.png" },
  { key: "aadhaar" as DocKey, label: "Aadhaar Card", icon: CreditCard, required: true, accept: ".pdf,.jpg,.jpeg,.png" },
  { key: "bank_statement" as DocKey, label: "Bank Statement (6 mo)", icon: Building2, required: true, accept: ".pdf" },
  { key: "salary_slip" as DocKey, label: "Salary Slips / Form 16", icon: Receipt, required: false, accept: ".pdf,.jpg,.jpeg,.png" },
];

export default function ApplyPage() {
  const [step, setStep] = useState(0);
  const [personal, setPersonal] = useState<PersonalInfo>(initialPersonal);
  const [employment, setEmployment] = useState<EmploymentInfo>(initialEmployment);
  const [loan, setLoan] = useState<LoanInfo>(initialLoan);
  const [docs, setDocs] = useState<UploadedDoc[]>([]);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const navigate = useNavigate();
  const { toast } = useToast();

  const validate = useCallback((): boolean => {
    const e: Record<string, string> = {};
    if (step === 0) {
      if (!personal.fullName.trim()) e.fullName = "Full name is required";
      if (!personal.dateOfBirth) e.dateOfBirth = "Date of birth is required";
      if (!/^\d{4}\s?\d{4}\s?\d{4}$/.test(personal.aadhaarNumber.replace(/\s/g,""))) e.aadhaarNumber = "Enter valid 12-digit Aadhaar";
      if (!/^[A-Z]{5}\d{4}[A-Z]$/.test(personal.panNumber.toUpperCase())) e.panNumber = "Enter valid PAN (e.g., ABCDE1234F)";
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(personal.email)) e.email = "Enter valid email";
      if (!/^\+?[\d\s]{10,13}$/.test(personal.phone.replace(/\s/g,""))) e.phone = "Enter valid phone number";
      if (!personal.address.trim()) e.address = "Address is required";
      if (!personal.city.trim()) e.city = "City is required";
      if (!personal.state) e.state = "State is required";
      if (!/^\d{6}$/.test(personal.pinCode)) e.pinCode = "Enter valid 6-digit PIN code";
    } else if (step === 1) {
      if (!employment.employmentStatus) e.employmentStatus = "Required";
      if (!employment.employerName.trim()) e.employerName = "Required";
      if (!employment.jobTitle.trim()) e.jobTitle = "Required";
      if (employment.monthlyIncome <= 0) e.monthlyIncome = "Enter valid income";
      if (employment.yearsAtJob < 0) e.yearsAtJob = "Enter valid years";
    } else if (step === 2) {
      if (loan.loanAmount <= 0) e.loanAmount = "Enter valid amount";
      if (!loan.loanPurpose.trim()) e.loanPurpose = "Required";
    } else if (step === 3) {
      if (!termsAccepted) e.terms = "You must accept the terms";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  }, [step, personal, employment, loan, termsAccepted]);

  const next = () => { if (validate()) setStep((s) => Math.min(s + 1, 3)); };
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  const handleSubmit = async () => {
    if (!validate()) return;

    try {
      // Map frontend form data to backend format
      const backendFormData = {
        applicant_name: personal.fullName,
        pan_number: personal.panNumber,
        aadhaar_last4: personal.aadhaarNumber.slice(-4),
        date_of_birth: personal.dateOfBirth,
        gender: "MALE", // Default for now
        employment_type: employment.employmentStatus.toUpperCase().includes("SALARIED") ? "SALARIED" : "SELF_EMPLOYED",
        employer_name: employment.employerName,
        annual_income: employment.monthlyIncome * 12,
        employment_tenure_years: employment.yearsAtJob,
        loan_amount_requested: loan.loanAmount,
        loan_tenure_months: loan.loanTerm,
        loan_purpose: loan.loanType.toUpperCase(),
        existing_emi_monthly: 0, // Parse from existingDebts if needed
        residential_assets_value: 0,
        mobile_number: personal.phone,
        email: personal.email,
        address: {
          line1: personal.address,
          city: personal.city,
          state: personal.state,
          pincode: personal.pinCode,
        },
        submitted_at: new Date().toISOString(),
      };

      const response = await submitApplicationAPI(backendFormData);
      navigate(`/apply/success?id=${response.application_id}`);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to submit application. Please try again.",
        variant: "destructive",
      });
      console.error("Submission error:", error);
    }
  };

  const handleSave = () => {
    localStorage.setItem("loan_draft", JSON.stringify({ personal, employment, loan, docs, step }));
    toast({ title: "Saved!", description: "Your progress has been saved. You can continue later." });
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    setDocs((prev) => [...prev, ...files.map((f) => ({ name: f.name, type: f.type, size: f.size }))]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const files = Array.from(e.target.files);
    setDocs((prev) => [...prev, ...files.map((f) => ({ name: f.name, type: f.type, size: f.size }))]);
  };

  const removeDoc = (idx: number) => setDocs((d) => d.filter((_, i) => i !== idx));

  const FieldError = ({ field }: { field: string }) => errors[field] ? <p className="text-destructive text-xs mt-1">{errors[field]}</p> : null;

  const updateP = (key: keyof PersonalInfo, val: string) => setPersonal((p) => ({ ...p, [key]: val }));
  const updateE = (key: keyof EmploymentInfo, val: any) => setEmployment((e) => ({ ...e, [key]: val }));
  const updateL = (key: keyof LoanInfo, val: any) => setLoan((l) => ({ ...l, [key]: val }));

  // ── Upload-mode ──────────────────────────────────────────────────────────
  const [mode, setMode] = useState<"choose" | "form" | "upload" | "preview">("choose");
  const tempUploadId = useMemo(() => `DRAFT-${Date.now()}`, []);
  const [uploadDocs, setUploadDocs] = useState<Record<DocKey, DocUploadState>>({
    aadhaar:        { file: null, status: "idle", result: null, error: null },
    pan:            { file: null, status: "idle", result: null, error: null },
    bank_statement: { file: null, status: "idle", result: null, error: null },
    salary_slip:    { file: null, status: "idle", result: null, error: null },
  });
  const uploadInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const setUpDoc = (key: DocKey, patch: Partial<DocUploadState>) =>
    setUploadDocs((d) => ({ ...d, [key]: { ...d[key], ...patch } }));

  const handleDocUpload = async (key: DocKey, file: File) => {
    setUpDoc(key, { file, status: "uploading", error: null });
    try {
      const fd = new FormData();
      fd.append("doc_type", key);
      fd.append("file", file);
      const res = await fetch(`/api/upload/${tempUploadId}`, { method: "POST", body: fd });
      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(e.detail || `HTTP ${res.status}`);
      }
      const data: Record<string, unknown> = await res.json();
      setUpDoc(key, { status: "done", result: data });
      const ef = (data.extracted_fields as Record<string, unknown>) || {};
      if (key === "pan") {
        if (ef.pan_number) updateP("panNumber", String(ef.pan_number));
        if (ef.name) updateP("fullName", String(ef.name));
        if (ef.date_of_birth) updateP("dateOfBirth", String(ef.date_of_birth));
      }
      if (key === "aadhaar") {
        if (ef.aadhaar_last4) updateP("aadhaarNumber", `XXXX XXXX ${String(ef.aadhaar_last4)}`);
        if (ef.pincode) updateP("pinCode", String(ef.pincode));
        if (ef.state) updateP("state", String(ef.state));
        if (ef.address) updateP("address", String(ef.address));
        // Aadhaar name takes priority (Gemini returns English-only name)
        if (ef.name) updateP("fullName", String(ef.name));
        if (ef.date_of_birth) updateP("dateOfBirth", String(ef.date_of_birth));
      }
      if (key === "bank_statement") {
        const inc = Number(ef.avg_monthly_credit);
        if (inc > 0) updateE("monthlyIncome", Math.round(inc));
      }
      if (key === "salary_slip") {
        const sal = Number(ef.net_salary) || Number(ef.gross_salary);
        if (sal > 0) updateE("monthlyIncome", Math.round(sal));
        if (ef.employer_name) updateE("employerName", String(ef.employer_name));
      }
      toast({ title: "Extracted", description: `${key.replace(/_/g, " ")} processed successfully.` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setUpDoc(key, { status: "error", error: msg });
      toast({ title: "Failed", description: msg, variant: "destructive" });
    }
  };

  const handlePreviewSubmit = async () => {
    if (!termsAccepted) {
      setErrors({ terms: "You must accept the terms" });
      return;
    }
    setErrors({});
    try {
      const backendFormData = {
        applicant_name: personal.fullName,
        pan_number: personal.panNumber,
        aadhaar_last4: personal.aadhaarNumber.replace(/\D/g, "").slice(-4) || personal.aadhaarNumber.slice(-4),
        date_of_birth: personal.dateOfBirth,
        gender: "MALE",
        employment_type: employment.employmentStatus.toUpperCase().includes("SALARIED") ? "SALARIED" : "SELF_EMPLOYED",
        employer_name: employment.employerName,
        annual_income: employment.monthlyIncome * 12,
        employment_tenure_years: employment.yearsAtJob,
        loan_amount_requested: loan.loanAmount,
        loan_tenure_months: loan.loanTerm,
        loan_purpose: loan.loanType.toUpperCase(),
        existing_emi_monthly: 0,
        residential_assets_value: 0,
        mobile_number: personal.phone,
        email: personal.email,
        address: { line1: personal.address, city: personal.city, state: personal.state, pincode: personal.pinCode },
        submitted_at: new Date().toISOString(),
      };
      const response = await submitApplicationAPI(backendFormData);
      navigate(`/apply/success?id=${response.application_id}`);
    } catch (error) {
      toast({ title: "Error", description: "Failed to submit application. Please try again.", variant: "destructive" });
      console.error("Submission error:", error);
    }
  };

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-10 max-w-3xl">
        <h1 className="text-3xl font-bold font-display text-foreground mb-6 text-center">Loan Application</h1>

        {/* Back to options */}
        {mode !== "choose" && (
          <button
            onClick={() => setMode("choose")}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to options
          </button>
        )}

        {/* ── Mode: Choose ─────────────────────────────────────────────── */}
        {mode === "choose" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4 animate-fade-in">
            <button
              onClick={() => setMode("form")}
              className="group text-left bg-card border-2 border-border hover:border-primary/60 rounded-xl p-7 shadow-card hover:shadow-elevated transition-all"
            >
              <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mb-5 group-hover:bg-primary/20 transition-colors">
                <FileText className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground text-lg mb-2">Fill Form Manually</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Enter your personal, employment and loan details step by step. Takes about 5 minutes.
              </p>
            </button>
            <button
              onClick={() => setMode("upload")}
              className="group text-left bg-card border-2 border-border hover:border-primary/60 rounded-xl p-7 shadow-card hover:shadow-elevated transition-all"
            >
              <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mb-5 group-hover:bg-primary/20 transition-colors">
                <Upload className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground text-lg mb-2">Upload Documents</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Upload PAN, Aadhaar, bank statement and salary slips. We'll auto-fill the form using OCR — then you review and edit.
              </p>
            </button>
          </div>
        )}

        {mode === "form" && (<>
        {/* Progress */}
        <div className="flex items-center justify-between mb-10">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-colors ${
                  i < step ? "bg-success text-success-foreground" : i === step ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                }`}>
                  {i < step ? <Check className="h-5 w-5" /> : i + 1}
                </div>
                <span className={`text-xs mt-2 text-center hidden sm:block ${i === step ? "text-primary font-semibold" : "text-muted-foreground"}`}>{s}</span>
              </div>
              {i < steps.length - 1 && <div className={`flex-1 h-0.5 mx-2 ${i < step ? "bg-success" : "bg-border"}`} />}
            </div>
          ))}
        </div>

        <Card className="shadow-elevated animate-fade-in">
          <CardHeader>
            <CardTitle className="font-display">{steps[step]}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {step === 0 && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div><Label>Full Name *</Label><Input value={personal.fullName} onChange={(e) => updateP("fullName", e.target.value)} placeholder="Enter your full name" /><FieldError field="fullName" /></div>
                  <div><Label>Date of Birth *</Label><Input type="date" value={personal.dateOfBirth} onChange={(e) => updateP("dateOfBirth", e.target.value)} /><FieldError field="dateOfBirth" /></div>
                  <div><Label>Aadhaar Number *</Label><Input value={personal.aadhaarNumber} onChange={(e) => updateP("aadhaarNumber", e.target.value)} placeholder="1234 5678 9012" /><FieldError field="aadhaarNumber" /></div>
                  <div><Label>PAN Number *</Label><Input value={personal.panNumber} onChange={(e) => updateP("panNumber", e.target.value.toUpperCase())} placeholder="ABCDE1234F" /><FieldError field="panNumber" /></div>
                  <div><Label>Email *</Label><Input type="email" value={personal.email} onChange={(e) => updateP("email", e.target.value)} placeholder="you@email.com" /><FieldError field="email" /></div>
                  <div><Label>Phone *</Label><Input value={personal.phone} onChange={(e) => updateP("phone", e.target.value)} placeholder="+91 98765 43210" /><FieldError field="phone" /></div>
                </div>
                <div><Label>Address *</Label><Textarea value={personal.address} onChange={(e) => updateP("address", e.target.value)} placeholder="Full address" /><FieldError field="address" /></div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div><Label>City *</Label><Input value={personal.city} onChange={(e) => updateP("city", e.target.value)} /><FieldError field="city" /></div>
                  <div>
                    <Label>State *</Label>
                    <Select value={personal.state} onValueChange={(v) => updateP("state", v)}>
                      <SelectTrigger><SelectValue placeholder="Select state" /></SelectTrigger>
                      <SelectContent>{indianStates.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                    </Select>
                    <FieldError field="state" />
                  </div>
                  <div><Label>PIN Code *</Label><Input value={personal.pinCode} onChange={(e) => updateP("pinCode", e.target.value)} placeholder="400001" /><FieldError field="pinCode" /></div>
                </div>
              </>
            )}

            {step === 1 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Employment Status *</Label>
                  <Select value={employment.employmentStatus} onValueChange={(v) => updateE("employmentStatus", v)}>
                    <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>
                      {["Salaried","Self-Employed","Business Owner","Freelancer","Retired","Student"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <FieldError field="employmentStatus" />
                </div>
                <div><Label>Employer Name *</Label><Input value={employment.employerName} onChange={(e) => updateE("employerName", e.target.value)} /><FieldError field="employerName" /></div>
                <div><Label>Job Title *</Label><Input value={employment.jobTitle} onChange={(e) => updateE("jobTitle", e.target.value)} /><FieldError field="jobTitle" /></div>
                <div><Label>Monthly Income (₹) *</Label><Input type="number" value={employment.monthlyIncome || ""} onChange={(e) => updateE("monthlyIncome", Number(e.target.value))} /><FieldError field="monthlyIncome" /></div>
                <div><Label>Years at Current Job *</Label><Input type="number" value={employment.yearsAtJob || ""} onChange={(e) => updateE("yearsAtJob", Number(e.target.value))} /><FieldError field="yearsAtJob" /></div>
                <div><Label>Additional Income Sources</Label><Input value={employment.additionalIncome} onChange={(e) => updateE("additionalIncome", e.target.value)} placeholder="e.g., Rental income" /></div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Loan Type *</Label>
                    <Select value={loan.loanType} onValueChange={(v) => updateL("loanType", v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{loanTypes.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Loan Amount (₹) *</Label><Input type="number" value={loan.loanAmount || ""} onChange={(e) => updateL("loanAmount", Number(e.target.value))} /><FieldError field="loanAmount" /></div>
                  <div>
                    <Label>Loan Term *</Label>
                    <Select value={String(loan.loanTerm)} onValueChange={(v) => updateL("loanTerm", Number(v))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{loanTerms.map((t) => <SelectItem key={t} value={String(t)}>{t} months</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <div><Label>Loan Purpose *</Label><Textarea value={loan.loanPurpose} onChange={(e) => updateL("loanPurpose", e.target.value)} placeholder="Describe the purpose" /><FieldError field="loanPurpose" /></div>
                <div><Label>Existing Debts / Liabilities</Label><Textarea value={loan.existingDebts} onChange={(e) => updateL("existingDebts", e.target.value)} placeholder="e.g., ₹15,000/month EMI" /></div>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-6">
                {/* File Upload */}
                <div>
                  <Label className="text-base font-semibold">Upload Documents</Label>
                  <div
                    className="mt-2 border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 hover:bg-muted/50 transition-colors"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleFileDrop}
                    onClick={() => document.getElementById("file-input")?.click()}
                  >
                    <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                    <p className="text-muted-foreground text-sm">Drag & drop files here or click to browse</p>
                    <p className="text-xs text-muted-foreground mt-1">ID Proof, Income Proof, Address Proof</p>
                    <input id="file-input" type="file" multiple className="hidden" onChange={handleFileSelect} />
                  </div>
                  {docs.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {docs.map((d, i) => (
                        <div key={i} className="flex items-center justify-between bg-muted rounded-md px-3 py-2 text-sm">
                          <span className="text-foreground truncate">{d.name}</span>
                          <button onClick={() => removeDoc(i)} className="text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Summary */}
                <div className="space-y-4">
                  <h3 className="font-semibold text-foreground">Application Summary</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <SummarySection title="Personal" items={[
                      ["Name", personal.fullName], ["DOB", personal.dateOfBirth], ["Aadhaar", personal.aadhaarNumber],
                      ["PAN", personal.panNumber], ["Email", personal.email], ["Phone", personal.phone],
                      ["City", personal.city], ["State", personal.state],
                    ]} />
                    <SummarySection title="Employment" items={[
                      ["Status", employment.employmentStatus], ["Employer", employment.employerName],
                      ["Income", `₹${employment.monthlyIncome.toLocaleString()}/mo`], ["Experience", `${employment.yearsAtJob} years`],
                    ]} />
                    <SummarySection title="Loan" items={[
                      ["Type", loan.loanType], ["Amount", `₹${loan.loanAmount.toLocaleString()}`],
                      ["Term", `${loan.loanTerm} months`], ["Purpose", loan.loanPurpose],
                    ]} />
                    <SummarySection title="Documents" items={docs.map((d, i) => [`File ${i + 1}`, d.name])} />
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <Checkbox id="terms" checked={termsAccepted} onCheckedChange={(v) => setTermsAccepted(!!v)} />
                  <label htmlFor="terms" className="text-sm text-muted-foreground leading-5">
                    I accept the <span className="text-primary underline cursor-pointer">Terms and Conditions</span> and confirm that all information provided is accurate.
                  </label>
                </div>
                <FieldError field="terms" />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-6">
          <div className="flex gap-2">
            {step > 0 && <Button variant="outline" onClick={prev}><ArrowLeft className="mr-2 h-4 w-4" /> Previous</Button>}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={handleSave}><Save className="mr-2 h-4 w-4" /> Save</Button>
            {step < 3 ? (
              <Button onClick={next}>Next <ArrowRight className="ml-2 h-4 w-4" /></Button>
            ) : (
              <Button onClick={handleSubmit} className="bg-success text-success-foreground hover:bg-success/90">Submit Application</Button>
            )}
          </div>
        </div>
        </>)}

        {mode === "upload" && (
          <div className="space-y-6 animate-fade-in">
            <p className="text-center text-sm text-muted-foreground mb-2">
              Upload your documents — data is auto-extracted and pre-fills the form.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {DOC_SLOTS.map((slot) => {
                const doc = uploadDocs[slot.key];
                const Icon = slot.icon;
                return (
                  <Card key={slot.key} className={`transition-all ${doc.status === "done" ? "border-success/40" : doc.status === "error" ? "border-destructive/40" : ""}`}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2 font-display">
                        <div className={`w-7 h-7 rounded-full flex items-center justify-center ${doc.status === "done" ? "bg-success/15" : "bg-primary/10"}`}>
                          {doc.status === "done" ? <CheckCircle2 className="h-3.5 w-3.5 text-success" /> : <Icon className="h-3.5 w-3.5 text-primary" />}
                        </div>
                        {slot.label}
                        {slot.required && <span className="text-xs text-destructive">*</span>}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 pt-0">
                      {doc.status !== "done" && (
                        <div
                          className="border-2 border-dashed border-border rounded p-3 text-center cursor-pointer hover:border-primary/40 hover:bg-primary/5 transition-colors"
                          onDragOver={(e) => e.preventDefault()}
                          onDrop={(e) => {
                            e.preventDefault();
                            const f = e.dataTransfer.files[0];
                            if (f) handleDocUpload(slot.key, f);
                          }}
                          onClick={() => uploadInputRefs.current[slot.key]?.click()}
                        >
                          <input
                            ref={(el) => { uploadInputRefs.current[slot.key] = el; }}
                            type="file"
                            accept={slot.accept}
                            className="hidden"
                            onChange={(e) => {
                              const f = e.target.files?.[0];
                              if (f) handleDocUpload(slot.key, f);
                            }}
                          />
                          {doc.status === "uploading" ? (
                            <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground py-1">
                              <Loader2 className="h-4 w-4 animate-spin" /> Processing…
                            </div>
                          ) : doc.file ? (
                            <span className="text-xs text-foreground truncate block">{doc.file.name}</span>
                          ) : (
                            <>
                              <Upload className="h-6 w-6 text-muted-foreground mx-auto mb-1" />
                              <p className="text-xs text-muted-foreground">Drop or <span className="text-primary">click</span></p>
                            </>
                          )}
                        </div>
                      )}
                      {doc.status === "error" && doc.error && (
                        <p className="text-xs text-destructive flex items-center gap-1">
                          <AlertCircle className="h-3 w-3" />{doc.error}
                        </p>
                      )}
                      {doc.status === "done" && (
                        <div className="text-xs text-success flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3" />&nbsp;{doc.file?.name}
                        </div>
                      )}
                      {doc.status === "done" && doc.result && (
                        Object.entries((doc.result.extracted_fields as Record<string, unknown>) || {})
                          .filter(([k, v]) => v && !k.startsWith("_") && k !== "sample_transactions")
                          .slice(0, 3).length > 0 && (
                          <div className="text-xs bg-success/5 border border-success/20 rounded p-2 space-y-0.5">
                            {Object.entries((doc.result.extracted_fields as Record<string, unknown>) || {})
                              .filter(([k, v]) => v && !k.startsWith("_") && k !== "sample_transactions")
                              .slice(0, 3)
                              .map(([k, v]) => (
                                <div key={k} className="flex justify-between gap-2">
                                  <span className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</span>
                                  <span className="font-mono text-foreground truncate max-w-[55%]">{String(v)}</span>
                                </div>
                              ))}
                          </div>
                        )
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
            <div className="flex justify-between items-center bg-card rounded-lg border border-border p-4 shadow-card">
              <div className="text-sm text-muted-foreground">
                {DOC_SLOTS.filter((s) => s.required).every((s) => uploadDocs[s.key].status === "done")
                  ? <span className="text-success font-medium flex items-center gap-1"><CheckCircle2 className="h-4 w-4" /> Required docs uploaded — form pre-filled</span>
                  : <span>{DOC_SLOTS.filter((s) => s.required && uploadDocs[s.key].status !== "done").length} required doc(s) pending</span>
                }
              </div>
              <Button onClick={() => setMode(Object.values(uploadDocs).some(d => d.status === "done") ? "preview" : "form")}>
                {Object.values(uploadDocs).some((d) => d.status === "done") ? "Preview & Edit →" : "Fill Form Manually →"}
              </Button>
            </div>
          </div>
        )}

        {/* ── Mode: Preview & Edit ─────────────────────────────────────── */}
        {mode === "preview" && (
          <div className="space-y-6 animate-fade-in">
            {/* Banner */}
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-primary mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-foreground">Review your extracted details</p>
                <p className="text-xs text-muted-foreground mt-0.5">Pre-filled from your uploaded documents. Edit any field before submitting.</p>
              </div>
              <button onClick={() => setMode("upload")} className="text-xs text-primary underline shrink-0 whitespace-nowrap">← Edit uploads</button>
            </div>

            {/* Personal */}
            <Card className="shadow-card">
              <CardHeader><CardTitle className="font-display text-base">Personal Information</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div><Label>Full Name *</Label><Input value={personal.fullName} onChange={(e) => updateP("fullName", e.target.value)} placeholder="Enter your full name" /></div>
                  <div><Label>Date of Birth *</Label><Input type="date" value={personal.dateOfBirth} onChange={(e) => updateP("dateOfBirth", e.target.value)} /></div>
                  <div><Label>Aadhaar Number *</Label><Input value={personal.aadhaarNumber} onChange={(e) => updateP("aadhaarNumber", e.target.value)} placeholder="1234 5678 9012" /></div>
                  <div><Label>PAN Number *</Label><Input value={personal.panNumber} onChange={(e) => updateP("panNumber", e.target.value.toUpperCase())} placeholder="ABCDE1234F" /></div>
                  <div><Label>Email *</Label><Input type="email" value={personal.email} onChange={(e) => updateP("email", e.target.value)} placeholder="you@email.com" /></div>
                  <div><Label>Phone *</Label><Input value={personal.phone} onChange={(e) => updateP("phone", e.target.value)} placeholder="+91 98765 43210" /></div>
                </div>
                <div><Label>Address *</Label><Textarea value={personal.address} onChange={(e) => updateP("address", e.target.value)} placeholder="Full address" /></div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div><Label>City *</Label><Input value={personal.city} onChange={(e) => updateP("city", e.target.value)} /></div>
                  <div>
                    <Label>State *</Label>
                    <Select value={personal.state} onValueChange={(v) => updateP("state", v)}>
                      <SelectTrigger><SelectValue placeholder="Select state" /></SelectTrigger>
                      <SelectContent>{indianStates.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>PIN Code *</Label><Input value={personal.pinCode} onChange={(e) => updateP("pinCode", e.target.value)} placeholder="400001" /></div>
                </div>
              </CardContent>
            </Card>

            {/* Employment */}
            <Card className="shadow-card">
              <CardHeader><CardTitle className="font-display text-base">Employment Details</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Employment Status *</Label>
                  <Select value={employment.employmentStatus} onValueChange={(v) => updateE("employmentStatus", v)}>
                    <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>
                      {["Salaried","Self-Employed","Business Owner","Freelancer","Retired","Student"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Employer Name *</Label><Input value={employment.employerName} onChange={(e) => updateE("employerName", e.target.value)} /></div>
                <div><Label>Job Title *</Label><Input value={employment.jobTitle} onChange={(e) => updateE("jobTitle", e.target.value)} /></div>
                <div><Label>Monthly Income (₹) *</Label><Input type="number" value={employment.monthlyIncome || ""} onChange={(e) => updateE("monthlyIncome", Number(e.target.value))} /></div>
                <div><Label>Years at Current Job</Label><Input type="number" value={employment.yearsAtJob || ""} onChange={(e) => updateE("yearsAtJob", Number(e.target.value))} /></div>
                <div><Label>Additional Income</Label><Input value={employment.additionalIncome} onChange={(e) => updateE("additionalIncome", e.target.value)} placeholder="e.g., Rental income" /></div>
              </CardContent>
            </Card>

            {/* Loan */}
            <Card className="shadow-card">
              <CardHeader><CardTitle className="font-display text-base">Loan Details</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Loan Type</Label>
                    <Select value={loan.loanType} onValueChange={(v) => updateL("loanType", v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{loanTypes.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div><Label>Loan Amount (₹) *</Label><Input type="number" value={loan.loanAmount || ""} onChange={(e) => updateL("loanAmount", Number(e.target.value))} /></div>
                  <div>
                    <Label>Loan Term</Label>
                    <Select value={String(loan.loanTerm)} onValueChange={(v) => updateL("loanTerm", Number(v))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>{loanTerms.map((t) => <SelectItem key={t} value={String(t)}>{t} months</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                  <div className="md:col-span-2"><Label>Loan Purpose *</Label><Textarea value={loan.loanPurpose} onChange={(e) => updateL("loanPurpose", e.target.value)} placeholder="Describe the purpose" /></div>
                  <div className="md:col-span-2"><Label>Existing Debts / Liabilities</Label><Textarea value={loan.existingDebts} onChange={(e) => updateL("existingDebts", e.target.value)} placeholder="e.g., ₹15,000/month EMI" /></div>
                </div>
              </CardContent>
            </Card>

            {/* Terms + Submit */}
            <div className="bg-card rounded-lg border border-border p-5 shadow-card space-y-4">
              <div className="flex items-start gap-2">
                <Checkbox id="terms-preview" checked={termsAccepted} onCheckedChange={(v) => setTermsAccepted(!!v)} />
                <label htmlFor="terms-preview" className="text-sm text-muted-foreground leading-5">
                  I accept the <span className="text-primary underline cursor-pointer">Terms and Conditions</span> and confirm that all information provided is accurate.
                </label>
              </div>
              <FieldError field="terms" />
              <div className="flex gap-3 justify-end">
                <Button variant="outline" onClick={() => setMode("upload")}><ArrowLeft className="h-4 w-4 mr-2" /> Back</Button>
                <Button onClick={handlePreviewSubmit} className="bg-success text-success-foreground hover:bg-success/90">Submit Application</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PublicLayout>
  );
}

function SummarySection({ title, items }: { title: string; items: string[][] }) {
  return (
    <div className="bg-muted rounded-lg p-4">
      <h4 className="font-semibold text-foreground mb-2">{title}</h4>
      {items.map(([k, v]) => (
        <div key={k} className="flex justify-between py-0.5">
          <span className="text-muted-foreground">{k}</span>
          <span className="text-foreground font-medium text-right max-w-[60%] truncate">{v || "—"}</span>
        </div>
      ))}
    </div>
  );
}
