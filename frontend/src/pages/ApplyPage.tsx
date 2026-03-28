import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Check, Upload, X, ArrowLeft, ArrowRight, Save } from "lucide-react";
import { submitApplication as submitApplicationAPI, extractDocuments } from "@/lib/api";
import { PersonalInfo, EmploymentInfo, LoanInfo, LoanType, LoanTerm, UploadedDoc } from "@/lib/types";
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react";

const steps = ["Personal Info", "Employment", "Loan Details", "Review & Submit"];
const loanTypes: LoanType[] = ["Personal"];
const loanTerms: LoanTerm[] = [12, 24, 36, 48, 60];
const indianStates = ["Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","Delhi","Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka","Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura","Uttar Pradesh","Uttarakhand","West Bengal"];

const initialPersonal: PersonalInfo = { fullName:"",dateOfBirth:"",gender:"MALE",aadhaarNumber:"",panNumber:"",email:"",phone:"",address:"",city:"",state:"",pinCode:"" };
const initialEmployment: EmploymentInfo = { employmentStatus:"",employerName:"",jobTitle:"",monthlyIncome:0,yearsAtJob:0,additionalIncome:"" };
const initialLoan: LoanInfo = { loanType:"Personal",loanAmount:0,loanPurpose:"",loanTerm:12,existingEmi:0,residentialAssets:0 };

export default function ApplyPage() {
  const [step, setStep] = useState(0);
  const [personal, setPersonal] = useState<PersonalInfo>(initialPersonal);
  const [employment, setEmployment] = useState<EmploymentInfo>(initialEmployment);
  const [loan, setLoan] = useState<LoanInfo>(initialLoan);
  const [docs, setDocs] = useState<File[]>([]);
  const [ocrData, setOcrData] = useState<any>(null);
  const [isProcessingOcr, setIsProcessingOcr] = useState(false);
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
      if (loan.existingEmi < 0) e.existingEmi = "Cannot be negative";
      if (loan.residentialAssets < 0) e.residentialAssets = "Cannot be negative";
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
        gender: personal.gender,
        employment_type: employment.employmentStatus.toUpperCase().includes("SALARIED") ? "SALARIED" : "SELF_EMPLOYED",
        employer_name: employment.employerName,
        annual_income: employment.monthlyIncome * 12,
        employment_tenure_years: employment.yearsAtJob,
        loan_amount_requested: loan.loanAmount,
        loan_tenure_months: loan.loanTerm,
        loan_purpose: loan.loanPurpose,
        loan_category: loan.loanType.toUpperCase(),
        existing_emi_monthly: loan.existingEmi,
        residential_assets_value: loan.residentialAssets,
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

      const response = await submitApplicationAPI({
        ...backendFormData,
        document_data: ocrData,
      });
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

  const handleFiles = async (newFiles: File[]) => {
    const updatedDocs = [...docs, ...newFiles];
    setDocs(updatedDocs);
    
    // Identify Aadhaar and PAN by filename or type if possible, 
    // but for PoC we can just try extracting from whatever was uploaded.
    const aadhaar = updatedDocs.find(f => f.name.toLowerCase().includes("aadhaar") || f.name.toLowerCase().includes("id"));
    const pan = updatedDocs.find(f => f.name.toLowerCase().includes("pan"));

    if (aadhaar || pan) {
      setIsProcessingOcr(true);
      toast({ title: "OCR Processing", description: "Extracting data from your documents..." });
      try {
        const data = await extractDocuments(aadhaar, pan);
        console.log("OCR Result:", data);
        setOcrData(data);
        
        // Auto-fill fields if they are empty
        if (data.name && !personal.fullName) updateP("fullName", data.name);
        if (data.pan_number && !personal.panNumber) updateP("panNumber", data.pan_number);
        if (data.aadhaar_number && !personal.aadhaarNumber) updateP("aadhaarNumber", data.aadhaar_number);

        toast({ title: "OCR Complete", description: "Successfully extracted data from documents." });
      } catch (err) {
        console.error("OCR Error:", err);
        toast({ title: "OCR Failed", description: "Could not extract data automatically.", variant: "destructive" });
      } finally {
        setIsProcessingOcr(false);
      }
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    handleFiles(Array.from(e.dataTransfer.files));
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    handleFiles(Array.from(e.target.files));
  };

  const removeDoc = (idx: number) => setDocs((d) => d.filter((_, i) => i !== idx));

  const FieldError = ({ field }: { field: string }) => errors[field] ? <p className="text-destructive text-xs mt-1">{errors[field]}</p> : null;

  const updateP = (key: keyof PersonalInfo, val: string) => setPersonal((p) => ({ ...p, [key]: val }));
  const updateE = (key: keyof EmploymentInfo, val: any) => setEmployment((e) => ({ ...e, [key]: val }));
  const updateL = (key: keyof LoanInfo, val: any) => setLoan((l) => ({ ...l, [key]: val }));

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-10 max-w-3xl">
        <h1 className="text-3xl font-bold font-display text-foreground mb-8 text-center">Loan Application</h1>

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
                  <div>
                    <Label>Gender *</Label>
                    <Select value={personal.gender} onValueChange={(v: any) => updateP("gender", v)}>
                      <SelectTrigger><SelectValue/></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="MALE">Male</SelectItem>
                        <SelectItem value="FEMALE">Female</SelectItem>
                        <SelectItem value="OTHER">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
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
                <div><Label>Monthly Income (₹) *</Label><Input type="number" value={employment.monthlyIncome || ""} onChange={(e) => updateE("monthlyIncome", Number(e.target.value))} /><FieldError field="monthlyIncome" /></div>
                <div><Label>Years at Current Job *</Label><Input type="number" value={employment.yearsAtJob || ""} onChange={(e) => updateE("yearsAtJob", Number(e.target.value))} /><FieldError field="yearsAtJob" /></div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Loan Category *</Label>
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
                <div><Label>Reason/Purpose for Loan *</Label><Textarea value={loan.loanPurpose} onChange={(e) => updateL("loanPurpose", e.target.value)} placeholder="Describe the purpose" /><FieldError field="loanPurpose" /></div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div><Label>Existing Monthly EMIs (₹)</Label><Input type="number" value={loan.existingEmi || 0} onChange={(e) => updateL("existingEmi", Number(e.target.value))} /><FieldError field="existingEmi" /></div>
                  <div><Label>Total Residential Asset Value (₹)</Label><Input type="number" value={loan.residentialAssets || 0} onChange={(e) => updateL("residentialAssets", Number(e.target.value))} /><FieldError field="residentialAssets" /></div>
                </div>
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
                    {isProcessingOcr ? (
                      <div className="flex flex-col items-center py-4">
                        <Loader2 className="h-10 w-10 text-primary animate-spin mb-3" />
                        <p className="text-muted-foreground text-sm">Processing documents with AI...</p>
                      </div>
                    ) : (
                      <>
                        <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                        <p className="text-muted-foreground text-sm">Drag & drop files here or click to browse</p>
                        <p className="text-xs text-muted-foreground mt-1">ID Proof, Income Proof, Address Proof</p>
                      </>
                    )}
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
                      ["Name", personal.fullName], ["DOB", personal.dateOfBirth], ["Gender", personal.gender],
                      ["Aadhaar", personal.aadhaarNumber], ["PAN", personal.panNumber], 
                      ["Email", personal.email], ["Phone", personal.phone],
                      ["City", personal.city], ["State", personal.state],
                    ]} />
                    <SummarySection title="Employment" items={[
                      ["Status", employment.employmentStatus], ["Employer", employment.employerName],
                      ["Income", `₹${employment.monthlyIncome.toLocaleString()}/mo`], ["Experience", `${employment.yearsAtJob} years`],
                    ]} />
                    <SummarySection title="Loan" items={[
                      ["Category", loan.loanType], ["Amount", `₹${loan.loanAmount.toLocaleString()}`],
                      ["Term", `${loan.loanTerm} months`], ["Purpose", loan.loanPurpose],
                      ["Monthly EMI", `₹${loan.existingEmi.toLocaleString()}`], ["Assets", `₹${loan.residentialAssets.toLocaleString()}`],
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
