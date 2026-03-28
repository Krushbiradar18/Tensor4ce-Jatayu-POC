export type LoanType = "Personal";
export type LoanTerm = 12 | 24 | 36 | 48 | 60;
export type ApplicationStatus = "Submitted" | "Under Review" | "Approved" | "Rejected" | "More Information Required";
export type AIDecision = "APPROVE" | "REJECT" | "REVIEW" | "ESCALATE";
export type OfficerDecision = "Pending" | "Approved" | "Rejected" | "Escalated" | "Under Review";

export interface PersonalInfo {
  fullName: string;
  dateOfBirth: string;
  gender: "MALE" | "FEMALE" | "OTHER";
  aadhaarNumber: string;
  panNumber: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  state: string;
  pinCode: string;
}

export interface EmploymentInfo {
  employmentStatus: string;
  employerName: string;
  jobTitle: string;
  monthlyIncome: number;
  yearsAtJob: number;
  additionalIncome: string;
}

export interface LoanInfo {
  loanType: LoanType;
  loanAmount: number;
  loanPurpose: string;
  loanTerm: LoanTerm;
  existingEmi: number;
  residentialAssets: number;
}

export interface UploadedDoc {
  name: string;
  type: string;
  size: number;
}

export interface AIAnalysis {
  decision: AIDecision;
  reason: string;
  creditRiskBand: string;
  probabilityOfDefault: number;
  foir: number;
  fraudLevel: string;
  compliance: string;
  elImpact: number;
  creditAgent: {
    riskScore: number;
    proposedEMI: number;
    surplusPerMonth: number;
    ltv: number;
    stress: string;
  };
  fraudAgent: {
    fraudProbability: number;
    softSignals: string[];
  };
  complianceAgent: {
    flags: string[];
  };
  portfolioAgent: {
    recommendation: string;
    sectorBefore: number;
    sectorAfter: number;
    geoAfter: number;
    similarNPARate: number;
    sectorBreach: string;
    elNote: string;
  };
}

export interface LoanApplication {
  id: string;
  personalInfo: PersonalInfo;
  employmentInfo: EmploymentInfo;
  loanInfo: LoanInfo;
  documents: UploadedDoc[];
  status: ApplicationStatus;
  aiAnalysis: AIAnalysis | null;
  officerDecision: OfficerDecision;
  officerNotes: string;
  submittedAt: string;
  updatedAt: string;
  termsAccepted: boolean;
}
