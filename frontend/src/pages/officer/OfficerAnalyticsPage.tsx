import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApplications } from "@/lib/store";

export default function OfficerAnalyticsPage() {
  const apps = useMemo(() => getApplications(), []);
  const total = apps.length;
  const approved = apps.filter((a) => a.status === "Approved").length;
  const rejected = apps.filter((a) => a.status === "Rejected").length;
  const pending = apps.filter((a) => a.status === "Under Review" || a.status === "Submitted").length;

  const byType = ["Personal", "Home", "Auto", "Business"].map((t) => ({
    type: t,
    count: apps.filter((a) => a.loanInfo.loanType === t).length,
    amount: apps.filter((a) => a.loanInfo.loanType === t).reduce((s, a) => s + a.loanInfo.loanAmount, 0),
  }));

  const avgAmount = total > 0 ? Math.round(apps.reduce((s, a) => s + a.loanInfo.loanAmount, 0) / total) : 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold font-display text-foreground">Analytics & Reports</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Approval Rate" value={`${total > 0 ? Math.round((approved / total) * 100) : 0}%`} sub={`${approved} of ${total}`} />
        <MetricCard title="Rejection Rate" value={`${total > 0 ? Math.round((rejected / total) * 100) : 0}%`} sub={`${rejected} of ${total}`} />
        <MetricCard title="Pending" value={String(pending)} sub="Applications awaiting" />
        <MetricCard title="Avg. Loan Amount" value={`₹${avgAmount.toLocaleString()}`} sub="Across all types" />
      </div>

      <Card className="shadow-card">
        <CardHeader><CardTitle className="font-display">Applications by Loan Type</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-4">
            {byType.map((t) => (
              <div key={t.type}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-foreground font-medium">{t.type}</span>
                  <span className="text-muted-foreground">{t.count} applications • ₹{t.amount.toLocaleString()}</span>
                </div>
                <div className="w-full bg-muted rounded-full h-3">
                  <div className="bg-primary rounded-full h-3 transition-all" style={{ width: `${total > 0 ? (t.count / total) * 100 : 0}%` }} />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ title, value, sub }: { title: string; value: string; sub: string }) {
  return (
    <Card className="shadow-card">
      <CardContent className="p-5">
        <p className="text-sm text-muted-foreground mb-1">{title}</p>
        <p className="text-3xl font-bold text-foreground">{value}</p>
        <p className="text-xs text-muted-foreground mt-1">{sub}</p>
      </CardContent>
    </Card>
  );
}
