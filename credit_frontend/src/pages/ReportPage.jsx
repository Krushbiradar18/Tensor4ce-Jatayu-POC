import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, AlertTriangle, XCircle, Shield } from 'lucide-react';

// ── Helpers (duplicated to keep page self-contained) ─────────────────────────
const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount);

const formatDate = (dateStr) =>
  new Date(dateStr).toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: 'numeric' });

const getRiskColor = (category) => {
  if (!category) return 'bg-gray-100 text-gray-700 border-gray-200';
  const c = category.toLowerCase();
  if (c.includes('low') && !c.includes('medium')) return 'bg-green-100 text-green-800 border-green-200';
  if (c.includes('medium-high') || (c.includes('high') && !c.includes('medium')))
    return 'bg-red-100 text-red-800 border-red-200';
  return 'bg-yellow-100 text-yellow-800 border-yellow-200';
};

const getRiskIcon = (category) => {
  if (!category) return <Shield className="h-6 w-6 text-gray-400" />;
  const c = category.toLowerCase();
  if (c.includes('low') && !c.includes('medium'))
    return <CheckCircle className="h-6 w-6 text-green-600" />;
  if (c.includes('high'))
    return <XCircle className="h-6 w-6 text-red-600" />;
  return <AlertTriangle className="h-6 w-6 text-yellow-600" />;
};

// ── Sub-components ────────────────────────────────────────────────────────────
const Section = ({ title, children }) => (
  <div className="mb-8">
    <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4 border-b border-gray-100 pb-2">
      {title}
    </h2>
    {children}
  </div>
);

const Field = ({ label, value, mono = false, highlight = false, large = false }) => (
  <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
    <p className="text-xs text-gray-400 mb-1">{label}</p>
    <p
      className={`font-semibold ${large ? 'text-2xl' : 'text-sm'} ${
        highlight ? 'text-primary-600' : 'text-gray-800'
      } ${mono ? 'font-mono' : ''}`}
    >
      {value}
    </p>
  </div>
);

// ── Main Page ─────────────────────────────────────────────────────────────────
const ReportPage = () => {
  const { state } = useLocation();
  const navigate  = useNavigate();

  if (!state?.app || !state?.result) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <p className="text-gray-500 mb-4">No report data found.</p>
          <button
            onClick={() => navigate('/applications')}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700"
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  const { app, result, profile } = state;

  const llmPoints = result.llm_explanation
    ? result.llm_explanation
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => /^\d+\./.test(l))
        .map((l) => l.replace(/^\d+\.\s*/, ''))
    : [];
  const showRawExplanation = llmPoints.length === 0 && result.llm_explanation;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4 sticky top-0 z-10 shadow-sm">
        <button
          onClick={() => navigate('/applications')}
          className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Applications
        </button>
        <div className="h-4 w-px bg-gray-300" />
        <div>
          <span className="text-sm font-semibold text-gray-900">Risk Assessment Report</span>
          <span className="ml-2 text-xs text-gray-400 font-mono">#{app.appId}</span>
        </div>
        <div className="ml-auto">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${getRiskColor(result.risk_category)}`}>
            {getRiskIcon(result.risk_category)}
            {result.risk_category}
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-4xl mx-auto px-6 py-10">

        {/* ── Applicant & Loan ── */}
        <Section title="Applicant & Loan Details">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Field label="Applicant Name"  value={profile?.name ?? app.applicantName} />
            <Field label="PAN"             value={profile?.pan  ?? app.pan} mono />
            <Field label="Application ID"  value={app.appId} mono />
            <Field label="Date"            value={formatDate(app.date)} />
            <Field label="Loan Type"       value={app.loanType} />
            <Field label="Loan Amount"     value={formatCurrency(app.loanAmount)} />
            <Field label="Tenure"          value={`${app.loanTenureMonths} months`} />
            <Field label="Monthly Income"  value={profile?.income ? formatCurrency(profile.income) : '—'} />
          </div>
        </Section>

        {/* ── Risk Summary ── */}
        <Section title="Risk Assessment Summary">
          <div className="grid grid-cols-3 gap-4">
            {/* Risk Score */}
            <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center shadow-sm">
              <p className="text-sm text-gray-400 mb-2">Risk Score</p>
              <p className="text-6xl font-extrabold text-gray-900 leading-none">
                {result.risk_score?.toFixed(1)}
              </p>
              <p className="text-xs text-gray-400 mt-2">out of 100</p>
            </div>

            {/* Category */}
            <div className={`rounded-2xl p-6 text-center border shadow-sm flex flex-col items-center justify-center gap-3 ${getRiskColor(result.risk_category)}`}>
              {getRiskIcon(result.risk_category)}
              <p className="text-xl font-bold">{result.risk_category}</p>
              <p className="text-xs opacity-70">Risk Category</p>
            </div>

            {/* EMI */}
            <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center shadow-sm">
              <p className="text-sm text-gray-400 mb-2">EMI Estimate</p>
              <p className="text-3xl font-extrabold text-gray-900">
                {result.emi_estimate ? formatCurrency(result.emi_estimate) : '—'}
              </p>
              <p className="text-xs text-gray-400 mt-2">/month</p>
            </div>
          </div>
        </Section>

        {/* ── Recommendation ── */}
        <Section title="Recommendation">
          <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm">
            <p className="text-lg font-semibold text-gray-800">{result.recommendation}</p>
          </div>
        </Section>

        {/* ── AI Explanation ── */}
        {result.llm_explanation && (
          <Section title="AI Assessment (SHAP-based)">
            <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm">
              {llmPoints.length > 0 ? (
                <ol className="space-y-4">
                  {llmPoints.map((point, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-7 h-7 rounded-full bg-primary-100 text-primary-700 text-sm font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-sm text-gray-700 leading-relaxed pt-1">{point}</span>
                    </li>
                  ))}
                </ol>
              ) : showRawExplanation ? (
                <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                  {result.llm_explanation}
                </p>
              ) : null}
            </div>
          </Section>
        )}

        {/* ── Credit Snapshot ── */}
        <Section title="Credit Snapshot">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Field label="CIBIL Score"         value={profile?.credit_score ?? result.credit_score ?? '—'} highlight />
            <Field label="Debt-to-Income"       value={result.debt_to_income_ratio != null ? `${(result.debt_to_income_ratio).toFixed(1)}%` : '—'} />
            <Field label="CC Utilisation"       value={result.utilization_summary?.CC_utilization != null ? `${result.utilization_summary.CC_utilization}%` : '—'} />
            <Field label="PL Utilisation"       value={result.utilization_summary?.PL_utilization != null ? `${result.utilization_summary.PL_utilization}%` : '—'} />
          </div>
        </Section>

        {/* Footer */}
        <p className="text-center text-xs text-gray-300 mt-10">
          Generated by LoanRisk AI · {new Date().toLocaleString('en-IN')}
        </p>
      </div>
    </div>
  );
};

export default ReportPage;
