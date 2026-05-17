const API_BASE = "/api";

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  needs_password_reset: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CreateAdminUserRequest {
  username: string;
  password: string;
  confirm_password: string;
  role: "officer" | "senior_officer";
  full_name?: string;
}

export interface PublicSignupRequest {
  username: string;
  password: string;
  confirm_password: string;
  full_name?: string;
}

export interface SignupOtpRequest {
  username: string;
  otp: string;
}

export interface LoginOtpRequest {
  challenge_id: number;
  otp: string;
}

export interface LoginChallengeResponse {
  success: boolean;
  token?: string;
  user?: AdminUser;
  requires_two_factor?: boolean;
  challenge_id?: number;
  method?: "email" | "authenticator";
  message?: string;
}

export interface SignupResponse {
  success: boolean;
  verification_required: boolean;
  message?: string;
  user?: AdminUser;
  token?: string;
}

export interface TwoFactorSettingsUpdateRequest {
  enabled: boolean;
  method: "email" | "authenticator";
}

export interface TotpSetupResponse {
  success: boolean;
  secret: string;
  otpauth_uri: string;
}

export interface TotpVerifyRequest {
  otp: string;
}

export interface SubmitApplicationRequest {
  form_data: Record<string, any>;
  ip_metadata: {
    ip_address: string;
    user_agent: string;
    timestamp: string;
  };
  document_data?: Record<string, any>;
}

export interface ApplicationResponse {
  application_id: string;
  status: string;
  message?: string;
  officer_decision?: string;
  officer_reason?: string;
  actioned_at?: string;
  decision?: {
    required_documents?: Array<{ doc: string; reason?: string; impact?: string; blocking?: boolean }>;
    officer_narrative?: string;
    data_completeness?: Record<string, any>;
    [key: string]: any;
  };
}

export interface OfficerQueueItem {
  application_id: string;
  status: string;
  raw_payload: string;
  ip_metadata: string;
  created_at: string;
  updated_at: string;
  applicant_name?: string;
  loan_purpose?: string;
  loan_amount?: number;
  ai_recommendation?: string;
  processing_ms?: number;
  processing_stage?: string;
}

export interface OfficerActionRequest {
  officer_id: string;
  decision: string;
  reason: string;
}

function getAuthHeaders(contentType: string = "application/json") {
  const token = localStorage.getItem("officer_token");
  const headers: Record<string, string> = {
    "Content-Type": contentType,
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export async function submitApplication(data: Record<string, any>): Promise<ApplicationResponse> {
  const { document_data, ...formData } = data;
  
  const response = await fetch(`${API_BASE}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      form_data: formData,
      ip_metadata: {
        ip_address: "127.0.0.1",
        user_agent: navigator.userAgent,
        timestamp: new Date().toISOString(),
      },
      document_data: document_data || {},
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to submit application: ${response.statusText}`);
  }

  return response.json();
}

export async function getApplicationStatus(appId: string): Promise<ApplicationResponse> {
  const response = await fetch(`${API_BASE}/status/${appId}`);

  if (!response.ok) {
    throw new Error(`Failed to get application status: ${response.statusText}`);
  }

  return response.json();
}

export async function resubmitDocuments(
  appId: string,
  annualIncome: number | null,
  files: { bankStatement?: File; salarySlip?: File; itr?: File; aadhaar?: File; pan?: File }
): Promise<ApplicationResponse> {
  const form = new FormData();
  if (annualIncome !== null) form.append("annual_income", String(annualIncome));
  if (files.bankStatement) form.append("bank_statement", files.bankStatement);
  if (files.salarySlip)    form.append("salary_slip", files.salarySlip);
  if (files.itr)           form.append("itr", files.itr);
  if (files.aadhaar)       form.append("aadhaar", files.aadhaar);
  if (files.pan)           form.append("pan", files.pan);

  const response = await fetch(`${API_BASE}/resubmit/${appId}`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(`Resubmit failed: ${response.statusText}`);
  }
  return response.json();
}

export async function getOfficerQueue(): Promise<OfficerQueueItem[]> {
  const response = await fetch(`${API_BASE}/officer/queue`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error(`Failed to get officer queue: ${response.statusText}`);
  }

  return response.json();
}

export async function getFullDecision(appId: string): Promise<any> {
  const response = await fetch(`${API_BASE}/officer/decision/${appId}`, {
    headers: getAuthHeaders()
  });

  if (!response.ok) {
    throw new Error(`Failed to get decision: ${response.statusText}`);
  }

  return response.json();
}

export async function submitOfficerAction(
  appId: string,
  action: OfficerActionRequest
): Promise<{ success: boolean; application_id: string; decision: string }> {
  const response = await fetch(`${API_BASE}/officer/action/${appId}`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(action),
  });

  if (!response.ok) {
    throw new Error(`Failed to submit officer action: ${response.statusText}`);
  }

  return response.json();
}

export async function extractDocuments(
  aadhaarFile?: File,
  panFile?: File,
  bankStatementFile?: File,
  salarySlipFile?: File,
  itrFile?: File
): Promise<any> {
  const formData = new FormData();
  if (aadhaarFile) formData.append("aadhaar", aadhaarFile);
  if (panFile) formData.append("pan", panFile);
  if (bankStatementFile) formData.append("bank_statement", bankStatementFile);
  if (salarySlipFile) formData.append("salary_slip", salarySlipFile);
  if (itrFile) formData.append("itr", itrFile);

  const response = await fetch(`${API_BASE}/extract-documents`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Failed to extract document data: ${response.statusText}`);
  }

  return response.json();
}

export async function loginOfficer(credentials: Record<string, string>): Promise<LoginChallengeResponse> {
  const response = await fetch(`${API_BASE}/officer/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(errorData.detail || `Failed to login: ${response.statusText}`);
  }

  return response.json();
}

export async function verifyLoginOtp(payload: LoginOtpRequest): Promise<LoginChallengeResponse> {
  const response = await fetch(`${API_BASE}/officer/login/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "OTP verification failed" }));
    throw new Error(errorData.detail || `Failed to verify OTP: ${response.statusText}`);
  }

  return response.json();
}

export async function publicSignup(payload: PublicSignupRequest): Promise<SignupResponse> {
  const response = await fetch(`${API_BASE}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Signup failed" }));
    throw new Error(errorData.detail || `Failed to sign up: ${response.statusText}`);
  }

  return response.json();
}

export async function verifySignupOtp(payload: SignupOtpRequest): Promise<SignupResponse> {
  const response = await fetch(`${API_BASE}/auth/signup/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "OTP verification failed" }));
    throw new Error(errorData.detail || `Failed to verify signup code: ${response.statusText}`);
  }

  return response.json();
}

export async function resendSignupOtp(payload: Pick<SignupOtpRequest, "username">): Promise<{ success: boolean; message?: string }> {
  const response = await fetch(`${API_BASE}/auth/signup/resend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to resend code" }));
    throw new Error(errorData.detail || `Failed to resend code: ${response.statusText}`);
  }

  return response.json();
}

export async function getAdminUsers(): Promise<AdminUser[]> {
  const response = await fetch(`${API_BASE}/admin/users`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to load users: ${response.statusText}`);
  }

  return response.json();
}

export async function createAdminUser(payload: CreateAdminUserRequest): Promise<{ success: boolean; user: AdminUser; message?: string }> {
  const response = await fetch(`${API_BASE}/admin/users`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to create user" }));
    throw new Error(errorData.detail || `Failed to create user: ${response.statusText}`);
  }

  return response.json();
}

export async function forgotPassword(username: string): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${API_BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to request password reset" }));
    throw new Error(errorData.detail || `Failed to request password reset: ${response.statusText}`);
  }

  return response.json();
}

export async function resetPassword(payload: { challenge_id: number; otp: string; new_password: string; confirm_password: string }): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${API_BASE}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to reset password" }));
    throw new Error(errorData.detail || `Failed to reset password: ${response.statusText}`);
  }

  return response.json();
}


export async function checkHealth(): Promise<any> {
  const response = await fetch(`${API_BASE}/health`);

  if (!response.ok) {
    throw new Error(`Failed to check health: ${response.statusText}`);
  }

  return response.json();
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  const response = await fetch(`${API_BASE}/users/admin/users`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to load users: ${response.statusText}`);
  }

  return response.json();
}

export async function createUser(
  username: string,
  password: string,
  role: "admin" | "officer" | "senior_officer",
  fullName?: string
): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/users/register`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      username,
      password,
      confirm_password: password,
      role,
      full_name: fullName || username,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to create user" }));
    throw new Error(errorData.detail || `Failed to create user: ${response.statusText}`);
  }

  return response.json();
}

export async function updateTwoFactorSettings(
  payload: TwoFactorSettingsUpdateRequest
): Promise<{ success: boolean; user: AdminUser & { two_factor_enabled?: boolean; two_factor_method?: string; is_verified?: boolean } }> {
  const response = await fetch(`${API_BASE}/officer/two-factor`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to update 2FA" }));
    throw new Error(errorData.detail || `Failed to update 2FA: ${response.statusText}`);
  }

  return response.json();
}

export async function setupTotpAuthenticator(): Promise<TotpSetupResponse> {
  const response = await fetch(`${API_BASE}/officer/two-factor/totp/setup`, {
    method: "POST",
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to start authenticator setup" }));
    throw new Error(errorData.detail || `Failed to start authenticator setup: ${response.statusText}`);
  }

  return response.json();
}

export async function verifyTotpAuthenticator(payload: TotpVerifyRequest): Promise<{ success: boolean; user: AdminUser & { two_factor_enabled?: boolean; two_factor_method?: string; is_verified?: boolean } }> {
  const response = await fetch(`${API_BASE}/officer/two-factor/totp/verify`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to verify authenticator code" }));
    throw new Error(errorData.detail || `Failed to verify authenticator code: ${response.statusText}`);
  }

  return response.json();
}

export async function updateUserRole(
  userId: number,
  newRole: "admin" | "officer" | "senior_officer"
): Promise<AdminUser> {
  const response = await fetch(`${API_BASE}/users/admin/users/${userId}/role`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ role: newRole }),
  });

  if (!response.ok) {
    throw new Error(`Failed to update user role: ${response.statusText}`);
  }

  return response.json();
}

export async function updateUserStatus(
  username: string,
  isActive: boolean
): Promise<{ success: boolean; user: AdminUser }> {
  const response = await fetch(`${API_BASE}/admin/users/${username}/status`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ is_active: isActive }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to update user status" }));
    throw new Error(errorData.detail || `Failed to update user status: ${response.statusText}`);
  }

  return response.json();
}

export async function updateUserRoleByUsername(
  username: string,
  newRole: string
): Promise<{ success: boolean; user: AdminUser }> {
  const response = await fetch(`${API_BASE}/admin/users/${username}/role`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify({ role: newRole }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to update user role" }));
    throw new Error(errorData.detail || `Failed to update user role: ${response.statusText}`);
  }

  return response.json();
}

export async function deleteUser(username: string): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${API_BASE}/admin/users/${username}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Failed to delete user" }));
    throw new Error(errorData.detail || `Failed to delete user: ${response.statusText}`);
  }

  return response.json();
}

// ── Logging API ─────────────────────────────────────────────────────────────

export interface LogEntry {
  id: number;
  timestamp: string;
  application_id?: string;
  agent_name: string;
  log_level: string;
  log_category: string;
  message: string;
  error_type?: string;
  stack_trace?: string;
  llm_model_name?: string;
  tool_name?: string;
  input_data?: string;
  output_data?: string;
  execution_time_ms?: number;
  metadata?: string;
  created_at: string;
}

export interface LogsResponse {
  total: number;
  page: number;
  limit: number;
  items: LogEntry[];
}

export async function fetchLogs(params: Record<string, any> = {}): Promise<LogsResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      query.append(k, String(v));
    }
  });
  
  const response = await fetch(`${API_BASE}/logs?${query.toString()}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch logs");
  return response.json();
}

export async function fetchLogStats(params: Record<string, any> = {}): Promise<any> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      query.append(k, String(v));
    }
  });

  const response = await fetch(`${API_BASE}/logs/stats?${query.toString()}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch log stats");
  return response.json();
}

export async function fetchLogHealth(): Promise<any> {
  const response = await fetch(`${API_BASE}/logs/health`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch log health");
  return response.json();
}

export async function fetchLogById(id: number): Promise<LogEntry> {
  const response = await fetch(`${API_BASE}/logs/${id}`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch log detail");
  return response.json();
}
