import axios from 'axios';

// Base API configuration — points directly at FastAPI backend (no /api prefix)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for handling errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// Check if backend is available
const checkBackendAvailability = async () => {
  try {
    await api.get('/health', { timeout: 3000 });
    return true;
  } catch (error) {
    return false;
  }
};

// API service methods — all calls go to the real FastAPI backend
export const apiService = {
  // Health check
  checkHealth: async () => {
    const response = await api.get('/health');
    return response.data;
  },

  // Fetch user profile by PAN number  →  GET /user/{pan}
  getUserProfile: async (pan) => {
    const response = await api.get(`/user/${pan.toUpperCase()}`);
    return response.data; // UserProfileResponse schema
  },

  // Full risk assessment  →  POST /assess-risk
  assessRisk: async ({ pan_number, loan_amount, loan_type, loan_tenure_months, declared_monthly_income }) => {
    const response = await api.post('/assess-risk', {
      pan_number,
      loan_amount,
      loan_type,
      loan_tenure_months,
      declared_monthly_income: declared_monthly_income ?? null,
    });
    return response.data; // RiskScoreResponse schema
  },

  // List all sample PANs  →  GET /sample-pans
  getSamplePans: async () => {
    const response = await api.get('/sample-pans');
    return response.data;
  },

  // List all DB users  →  GET /db/users
  getDbUsers: async () => {
    const response = await api.get('/db/users');
    return response.data;
  },

  // Create DB user  →  POST /db/users
  createDbUser: async (payload) => {
    const response = await api.post('/db/users', payload);
    return response.data;
  },

  // Model info  →  GET /model/info
  getModelInfo: async () => {
    const response = await api.get('/model/info');
    return response.data;
  },
};

export default api;