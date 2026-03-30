const API_BASE = "/api";

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

export async function extractDocuments(aadhaarFile?: File, panFile?: File): Promise<any> {
  const formData = new FormData();
  if (aadhaarFile) formData.append("aadhaar", aadhaarFile);
  if (panFile) formData.append("pan", panFile);

  const response = await fetch(`${API_BASE}/extract-documents`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Failed to extract document data: ${response.statusText}`);
  }

  return response.json();
}

export async function loginOfficer(credentials: Record<string, string>): Promise<any> {
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

export async function checkHealth(): Promise<any> {
  const response = await fetch(`${API_BASE}/health`);

  if (!response.ok) {
    throw new Error(`Failed to check health: ${response.statusText}`);
  }

  return response.json();
}
