import { LoanApplication, AIAnalysis, ApplicationStatus, OfficerDecision } from "./types";

const STORAGE_KEY = "loan_applications";

function generateId(): string {
  const prefix = "BNK";
  const num = Math.floor(100000 + Math.random() * 900000);
  return `${prefix}${num}`;
}

function generateAIAnalysis(app: LoanApplication): AIAnalysis {
  const income = app.employmentInfo.monthlyIncome;
  const amount = app.loanInfo.loanAmount;
  const emi = amount / (app.loanInfo.loanTerm);
  const foir = (emi / income) * 100;
  const isHighRisk = foir > 55 || income < 25000;
  const pd = isHighRisk ? 25 + Math.random() * 15 : 3 + Math.random() * 10;

  return {
    decision: isHighRisk ? "REJECT" : foir > 40 ? "REVIEW" : "APPROVE",
    reason: isHighRisk
      ? "Rejected due to high FOIR and compliance policy concerns"
      : foir > 40
      ? "Application requires manual review due to moderate risk indicators"
      : "Application meets all credit and compliance criteria",
    creditRiskBand: isHighRisk ? "VERY_HIGH" : foir > 40 ? "MODERATE" : "LOW",
    probabilityOfDefault: Math.round(pd * 10) / 10,
    foir: Math.round(foir * 10) / 10,
    fraudLevel: "CLEAN",
    compliance: isHighRisk ? "BLOCK_FAIL" : "PASS",
    elImpact: Math.round(amount * (pd / 100) * 0.45),
    creditAgent: {
      riskScore: isHighRisk ? Math.round(Math.random() * 30) : Math.round(60 + Math.random() * 35),
      proposedEMI: Math.round(emi),
      surplusPerMonth: Math.round(income - emi - income * 0.4),
      ltv: app.loanInfo.loanType === "Home" ? Math.round(70 + Math.random() * 20) : 0,
      stress: isHighRisk ? "HIGH" : "NORMAL",
    },
    fraudAgent: {
      fraudProbability: Math.round((2 + Math.random() * 8) * 10) / 10,
      softSignals: ["New Device: Unrecognised Device Fingerprint"],
    },
    complianceAgent: {
      flags: isHighRisk ? [`FOIR ${Math.round(foir * 10) / 10}% Exceeds 55% RBI Limit`] : [],
    },
    portfolioAgent: {
      recommendation: isHighRisk ? "REJECT_FOR_PORTFOLIO" : "ACCEPT",
      sectorBefore: 82,
      sectorAfter: 85,
      geoAfter: 19.7,
      similarNPARate: 2.7,
      sectorBreach: app.loanInfo.loanType === "Home" ? "Home At 85% > 40% Limit" : "",
      elNote: "EL impact is incremental expected loss for this single loan (EL = PD × LGD × Loan Amount), not total portfolio loss.",
    },
  };
}

export function getApplications(): LoanApplication[] {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw ? JSON.parse(raw) : getSeedData();
}

function saveApplications(apps: LoanApplication[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(apps));
}

export function submitApplication(data: Omit<LoanApplication, "id" | "status" | "aiAnalysis" | "officerDecision" | "officerNotes" | "submittedAt" | "updatedAt">): string {
  const apps = getApplications();
  const id = generateId();
  const now = new Date().toISOString();
  const newApp: LoanApplication = {
    ...data,
    id,
    status: "Submitted",
    aiAnalysis: null,
    officerDecision: "Pending",
    officerNotes: "",
    submittedAt: now,
    updatedAt: now,
  };
  // Generate AI analysis after short delay simulation
  newApp.aiAnalysis = generateAIAnalysis(newApp);
  newApp.status = "Under Review";
  apps.push(newApp);
  saveApplications(apps);
  return id;
}

export function getApplicationById(id: string): LoanApplication | undefined {
  return getApplications().find((a) => a.id === id);
}

export function updateOfficerDecision(id: string, decision: OfficerDecision, notes: string) {
  const apps = getApplications();
  const idx = apps.findIndex((a) => a.id === id);
  if (idx === -1) return;
  const statusMap: Record<OfficerDecision, ApplicationStatus> = {
    Pending: "Under Review",
    "Under Review": "Under Review",
    Approved: "Approved",
    Rejected: "Rejected",
    Escalated: "More Information Required",
  };
  apps[idx].officerDecision = decision;
  apps[idx].officerNotes = notes;
  apps[idx].status = statusMap[decision];
  apps[idx].updatedAt = new Date().toISOString();
  saveApplications(apps);
}

function getSeedData(): LoanApplication[] {
  const seeds: LoanApplication[] = [
    createSeed("BNK100001", "Rajesh Kumar", "Personal", 500000, 45000, "Submitted", "Pending", 36),
    createSeed("BNK100002", "Priya Sharma", "Home", 3500000, 95000, "Under Review", "Pending", 60),
    createSeed("BNK100003", "Amit Patel", "Auto", 800000, 55000, "Approved", "Approved", 48),
    createSeed("BNK100004", "Sneha Reddy", "Business", 1500000, 120000, "Rejected", "Rejected", 24),
    createSeed("BNK100005", "Vikram Singh", "Personal", 200000, 30000, "Under Review", "Pending", 12),
    createSeed("BNK100006", "Anita Desai", "Home", 5000000, 150000, "Approved", "Approved", 60),
    createSeed("BNK100007", "Ravi Gupta", "Auto", 600000, 40000, "More Information Required", "Escalated", 36),
    createSeed("BNK100008", "Meera Joshi", "Personal", 300000, 35000, "Submitted", "Pending", 24),
  ];
  saveApplications(seeds);
  return seeds;
}

function createSeed(id: string, name: string, loanType: string, amount: number, income: number, status: ApplicationStatus, officerDec: OfficerDecision, term: number): LoanApplication {
  const daysAgo = Math.floor(Math.random() * 30);
  const date = new Date(Date.now() - daysAgo * 86400000).toISOString();
  const app: LoanApplication = {
    id,
    personalInfo: {
      fullName: name,
      dateOfBirth: "1990-05-15",
      aadhaarNumber: "1234 5678 9012",
      panNumber: "ABCDE1234F",
      email: `${name.toLowerCase().replace(/\s/g, ".")}@email.com`,
      phone: "+91 98765 43210",
      address: "123, MG Road, Sector 14",
      city: "Mumbai",
      state: "Maharashtra",
      pinCode: "400001",
    },
    employmentInfo: {
      employmentStatus: "Salaried",
      employerName: "TechCorp India Ltd",
      jobTitle: "Senior Analyst",
      monthlyIncome: income,
      yearsAtJob: 4,
      additionalIncome: "None",
    },
    loanInfo: {
      loanType: loanType as any,
      loanAmount: amount,
      loanPurpose: `${loanType} loan requirement`,
      loanTerm: term as any,
      existingDebts: "₹15,000/month EMI",
    },
    documents: [
      { name: "Aadhaar_Card.pdf", type: "application/pdf", size: 245000 },
      { name: "PAN_Card.pdf", type: "application/pdf", size: 180000 },
      { name: "Salary_Slip.pdf", type: "application/pdf", size: 320000 },
    ],
    status,
    aiAnalysis: null,
    officerDecision: officerDec,
    officerNotes: officerDec === "Approved" ? "All documents verified. Application meets criteria." : officerDec === "Rejected" ? "High risk profile. FOIR exceeds limit." : "",
    submittedAt: date,
    updatedAt: date,
    termsAccepted: true,
  };
  app.aiAnalysis = generateAIAnalysis(app);
  return app;
}
