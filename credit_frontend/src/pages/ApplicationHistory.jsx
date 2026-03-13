import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, Send, CheckCircle, ChevronDown, ChevronUp, AlertCircle, TrendingUp, TrendingDown, Loader2 } from 'lucide-react';
import { apiService } from '../services/api';

const toAppId = (pan, idx) => {
  const seed = [...(pan || '')].reduce((acc, ch) => acc + ch.charCodeAt(0), 0) + idx * 97;
  return String(10000000 + (seed % 89999999));
};

const toApplication = (user, idx) => {
  const pan = (user.pan || '').toUpperCase();
  const name = user.name || `Applicant ${idx + 1}`;
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const monthlyIncome = Number(user.NETMONTHLYINCOME ?? user.income ?? 0);
  const suggestedLoan = Math.max(100000, Math.round((monthlyIncome * 8) / 1000) * 1000 || 500000);

  return {
    id: pan,
    appId: toAppId(pan, idx),
    applicantName: name,
    filename: `loan_app_${slug || `user_${idx + 1}`}.pdf`,
    pan,
    date: new Date().toISOString().slice(0, 10),
    loanAmount: suggestedLoan,
    loanType: 'Personal Loan',
    loanTenureMonths: 36,
    status: 'pending',
    result: null,
    profile: {
      pan,
      name,
      age: user.AGE ?? user.age,
      income: user.NETMONTHLYINCOME ?? user.income,
      credit_score: user.Credit_Score ?? user.credit_score,
    },
  };
};

// ── Helpers ──────────────────────────────────────────────────────────────────
const formatDate = (dateStr) =>
  new Date(dateStr).toLocaleDateString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount);

const getRiskColor = (category) => {
  if (!category) return 'bg-gray-100 text-gray-700';
  const c = category.toLowerCase();
  if (c.includes('low') && !c.includes('medium')) return 'bg-green-100 text-green-800';
  if (c.includes('medium-high') || c.includes('high')) return 'bg-red-100 text-red-800';
  return 'bg-yellow-100 text-yellow-800';
};

const getFlagColor = (flag) => {
  if (flag === 'P4') return 'text-green-600';
  if (flag === 'P3') return 'text-yellow-600';
  if (flag === 'P2') return 'text-orange-500';
  return 'text-red-600';
};

const ApplicationHistory = () => {
  const navigate = useNavigate();
  const [applications, setApplications] = useState([]);
  const [loadingApps, setLoadingApps] = useState(true);
  const [listError, setListError] = useState(null);

  useEffect(() => {
    const fetchApplications = async () => {
      setLoadingApps(true);
      setListError(null);
      try {
        const [usersResp, processedResp] = await Promise.all([
          apiService.getDbUsers(),
          apiService.getProcessedResults(),
        ]);
        const users = Array.isArray(usersResp?.users) ? usersResp.users : [];
        const processed = Array.isArray(processedResp?.processed) ? processedResp.processed : [];
        const processedMap = Object.fromEntries(processed.map((r) => [String(r.pan).toUpperCase(), r]));

        const baseApps = users.map(toApplication);
        const merged = baseApps.map((app) => {
          const saved = processedMap[app.pan];
          return saved
            ? { ...app, status: saved.status || 'completed', result: saved.result || null }
            : app;
        });
        setApplications(merged);
      } catch (err) {
        setListError('Failed to load applications from database.');
      } finally {
        setLoadingApps(false);
      }
    };

    fetchApplications();
  }, []);

  const [expandedId, setExpandedId]   = useState(null);
  const [loadingProfile, setLoadingProfile] = useState({});
  const [loadingSubmit, setLoadingSubmit] = useState({});
  const [errors, setErrors] = useState({});

  // ── Toggle expanded row ────────────────────────────────────────────────────
  const handleView = async (app) => {
    // Collapse if already open
    if (expandedId === app.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(app.id);

    // Fetch user profile only if not yet cached
    if (!app.profile) {
      setLoadingProfile((prev) => ({ ...prev, [app.id]: true }));
      try {
        const profile = await apiService.getUserProfile(app.pan);
        setApplications((prev) =>
          prev.map((a) => (a.id === app.id ? { ...a, profile } : a))
        );
      } catch (err) {
        setErrors((prev) => ({ ...prev, [app.id]: 'Failed to load user profile.' }));
      } finally {
        setLoadingProfile((prev) => ({ ...prev, [app.id]: false }));
      }
    }
  };

  // ── Submit for risk assessment ─────────────────────────────────────────────
  const handleSubmit = async (app) => {
    setLoadingSubmit((prev) => ({ ...prev, [app.id]: true }));
    setErrors((prev) => ({ ...prev, [app.id]: null }));
    try {
      await apiService.assessRisk({
        pan_number: app.pan,
        loan_amount: app.loanAmount,
        loan_type: app.loanType,
        loan_tenure_months: app.loanTenureMonths,
        declared_monthly_income: null,
      });

      const processedRecord = await apiService.getProcessedResultByPan(app.pan);
      const result = processedRecord?.result || null;

      // Build the complete updated app (profile may already be loaded from a prior View click)
      const updatedApp = { ...app, status: 'completed', result };

      // Compute the full updated list
      const updatedApps = applications.map((a) => (a.id === app.id ? updatedApp : a));
      setApplications(updatedApps);
      setExpandedId(app.id);

      // Navigate to full-page report
      navigate('/report', {
        state: {
          app: updatedApp,
          result,
          profile: app.profile,
        },
      });
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || 'Risk assessment failed.';
      setErrors((prev) => ({ ...prev, [app.id]: typeof msg === 'string' ? msg : JSON.stringify(msg) }));
    } finally {
      setLoadingSubmit((prev) => ({ ...prev, [app.id]: false }));
    }
  };

  // ── Status badge ───────────────────────────────────────────────────────────
  const StatusBadge = ({ status }) => {
    if (status === 'completed')
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">
          <CheckCircle className="h-3 w-3" /> Completed
        </span>
      );
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 border border-yellow-200">
        Pending
      </span>
    );
  };

  // ── Expanded panel ─────────────────────────────────────────────────────────
  const ExpandedPanel = ({ app }) => {
    const profile = app.profile;
    const result  = app.result;
    const isLoadingP = loadingProfile[app.id];
    const isLoadingS = loadingSubmit[app.id];
    const error = errors[app.id];

    return (
      <tr className="bg-blue-50">
        <td colSpan={6} className="px-6 py-5">
          <div className="space-y-6">
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                {error}
              </div>
            )}

            {/* ── User Information ── */}
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">User Information</h3>
              {isLoadingP ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading profile…
                </div>
              ) : profile ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <InfoCard label="Name"         value={profile.name ?? '—'} />
                  <InfoCard label="PAN"          value={profile.pan ?? '—'} mono />
                  <InfoCard label="Application ID" value={app.appId} mono />
                  <InfoCard label="Credit Score"  value={profile.credit_score ?? '—'} highlight />
                  <InfoCard label="Age"           value={profile.age ? `${profile.age} yrs` : '—'} />
                  <InfoCard label="Monthly Income" value={profile.income ? formatCurrency(profile.income) : '—'} />
                  <InfoCard label="Loan Amount"   value={formatCurrency(app.loanAmount)} />
                  <InfoCard label="Loan Tenure"   value={`${app.loanTenureMonths} months`} />
                </div>
              ) : (
                <p className="text-sm text-gray-400 italic">Profile not loaded.</p>
              )}
            </div>

            {/* ── Risk Assessment Result ── */}
            {result && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Risk Assessment Result</h3>

                {/* Summary cards */}
                <div className="grid grid-cols-3 gap-4 mb-5">
                  <div className="bg-white rounded-lg border border-gray-200 p-6 text-center shadow-sm">
                    <p className="text-sm text-gray-500 mb-2">Risk Score</p>
                    <p className="text-5xl font-bold text-gray-900">{result.risk_score?.toFixed(1)}</p>
                    <p className="text-sm text-gray-400 mt-2">out of 100</p>
                  </div>
                  <div className="bg-white rounded-lg border border-gray-200 p-6 text-center shadow-sm flex flex-col items-center justify-center">
                    <p className="text-sm text-gray-500 mb-3">Category</p>
                    <span className={`inline-block px-4 py-2 rounded-full text-base font-semibold ${getRiskColor(result.risk_category)}`}>
                      {result.risk_category}
                    </span>
                  </div>
                  <div className="bg-white rounded-lg border border-gray-200 p-6 text-center shadow-sm">
                    <p className="text-sm text-gray-500 mb-2">EMI Estimate</p>
                    <p className="text-3xl font-bold text-gray-900">{result.emi_estimate ? formatCurrency(result.emi_estimate) : '—'}</p>
                    <p className="text-sm text-gray-400 mt-2">/month</p>
                  </div>
                </div>

                {/* Recommendation */}
                <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 shadow-sm">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Recommendation</p>
                  <p className="text-base font-medium text-gray-800 capitalize">{result.recommendation}</p>
                </div>

                {/* LLM Explanation */}
                {result.llm_explanation && (
                  <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 shadow-sm">
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">AI Explaination</p>
                    <ol className="space-y-2">
                      {result.llm_explanation
                        .split('\n')
                        .map(line => line.trim())
                        .filter(line => /^\d+\./.test(line))
                        .map((line, i) => {
                          const text = line.replace(/^\d+\.\s*/, '');
                          return (
                            <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary-100 text-primary-700 text-xs font-bold flex items-center justify-center mt-0.5">
                                {i + 1}
                              </span>
                              <span className="leading-relaxed">{text}</span>
                            </li>
                          );
                        })}
                    </ol>
                    {/* fallback: if AI didn't return numbered list, show raw */}
                    {!/^\d+\./m.test(result.llm_explanation) && (
                      <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{result.llm_explanation}</p>
                    )}
                  </div>
                )}


              </div>
            )}
          </div>
        </td>
      </tr>
    );
  };

  return (
    <div className="flex-1">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h1 className="text-2xl font-semibold text-gray-900">Application History</h1>
        <p className="text-sm text-gray-500 mt-1">View and process loan application risk assessments</p>
      </div>

      {/* Table */}
      <div className="p-6">
        {listError && (
          <div className="mb-4 flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            {listError}
          </div>
        )}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {['Application', 'ID', 'Date', 'Status', 'Risk Score', 'Actions'].map((h) => (
                    <th
                      key={h}
                      className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loadingApps && (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                      <span className="inline-flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" /> Loading applications from database...
                      </span>
                    </td>
                  </tr>
                )}
                {applications.map((app) => {
                  const isExpanded = expandedId === app.id;
                  const isLoadingS = loadingSubmit[app.id];
                  const processed  = app.status === 'completed';

                  return (
                    <React.Fragment key={app.id}>
                      <tr className={`hover:bg-gray-50 transition-colors ${isExpanded ? 'bg-blue-50/40' : ''}`}>
                        {/* Application */}
                        <td className="px-6 py-4">
                          <p className="text-base font-semibold text-gray-900">{app.filename.replace(/\.pdf$/i, '')}</p>
                          <p className="text-sm text-gray-500 mt-0.5">{app.applicantName}</p>
                        </td>

                        {/* ID */}
                        <td className="px-6 py-4 text-sm text-gray-600 font-mono">{app.appId}</td>

                        {/* Date */}
                        <td className="px-6 py-4 text-sm text-gray-600">{formatDate(app.date)}</td>

                        {/* Status */}
                        <td className="px-6 py-4">
                          <StatusBadge status={app.status} />
                        </td>

                        {/* Risk Score */}
                        <td className="px-6 py-4">
                          {processed && app.result ? (
                            <div className="flex flex-col gap-1">
                              <span className="text-lg font-bold text-gray-900">
                                {app.result.risk_score?.toFixed(1)}
                              </span>
                              <span className={`text-xs px-2 py-0.5 rounded-full font-medium w-fit ${getRiskColor(app.result.risk_category)}`}>
                                {app.result.risk_category}
                              </span>
                            </div>
                          ) : (
                            <span className="text-gray-400 text-sm">—</span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            {/* View button */}
                            <button
                              onClick={() => handleView(app)}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg transition-colors"
                            >
                              <Eye className="h-3.5 w-3.5" />
                              View
                              {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            </button>

                            {/* Submit / Processed */}
                            {processed ? (
                              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-lg">
                                <CheckCircle className="h-3.5 w-3.5" />
                                Processed
                              </span>
                            ) : (
                              <button
                                onClick={() => handleSubmit(app)}
                                disabled={isLoadingS}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg transition-colors"
                              >
                                {isLoadingS ? (
                                  <>
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    Processing…
                                  </>
                                ) : (
                                  <>
                                    <Send className="h-3.5 w-3.5" />
                                    Submit
                                  </>
                                )}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>

                      {/* Expanded detail panel */}
                      {isExpanded && <ExpandedPanel app={app} />}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Small helpers ────────────────────────────────────────────────────────────
const InfoCard = ({ label, value, mono = false, highlight = false }) => (
  <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
    <p className="text-xs text-gray-500 mb-0.5">{label}</p>
    <p className={`text-sm font-semibold ${highlight ? 'text-primary-600' : 'text-gray-800'} ${mono ? 'font-mono' : ''}`}>
      {value}
    </p>
  </div>
);

const FactorList = ({ title, factors, type }) => (
  <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
    <div className="flex items-center gap-1.5 mb-3">
      {type === 'risk' ? (
        <TrendingUp className="h-4 w-4 text-red-500" />
      ) : (
        <TrendingDown className="h-4 w-4 text-green-500" />
      )}
      <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{title}</p>
    </div>
    <ul className="space-y-2">
      {factors.slice(0, 5).map((f, i) => (
        <li key={i} className="flex items-start gap-2 text-sm">
          <span
            className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${
              type === 'risk' ? 'bg-red-400' : 'bg-green-400'
            }`}
          />
          <div>
            <span className="font-medium text-gray-700">{f.feature}</span>
            {f.description && (
              <p className="text-xs text-gray-400 mt-0.5">{f.description}</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  </div>
);

export default ApplicationHistory;
