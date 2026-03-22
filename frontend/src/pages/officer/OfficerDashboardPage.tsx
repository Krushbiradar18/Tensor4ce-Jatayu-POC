import { useMemo, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileText, Clock, CheckCircle, XCircle, TrendingUp, TrendingDown, Eye } from "lucide-react";
import { getOfficerQueue } from "@/lib/api";
import { ApplicationStatus } from "@/lib/types";

const statusColors: Record<string, string> = {
  "PENDING": "bg-info/15 text-info border border-info/20",
  "DIL_PROCESSING": "bg-info/15 text-info border border-info/20",
  "AGENTS_RUNNING": "bg-warning/15 text-warning-foreground border border-warning/20",
  "DECIDED_PENDING_OFFICER": "bg-warning/15 text-warning-foreground border border-warning/20",
  "OFFICER_APPROVED": "bg-success/15 text-success border border-success/20",
  "OFFICER_REJECTED": "bg-destructive/15 text-destructive border border-destructive/20",
  "OFFICER_CONDITIONAL": "bg-accent/15 text-accent-foreground border border-accent/20",
  "OFFICER_ESCALATED": "bg-accent/15 text-accent-foreground border border-accent/20",
  "ERROR": "bg-destructive/15 text-destructive border border-destructive/20",
};

export default function OfficerDashboardPage() {
  const [apps, setApps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getOfficerQueue()
      .then((data) => {
        setApps(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch officer queue:", err);
        setLoading(false);
      });
  }, []);

  const total = apps.length;
  const pending = apps.filter((a) => a.status === "PENDING" || a.status === "DIL_PROCESSING" || a.status === "AGENTS_RUNNING" || a.status === "DECIDED_PENDING_OFFICER").length;
  const approved = apps.filter((a) => a.status === "OFFICER_APPROVED").length;
  const rejected = apps.filter((a) => a.status === "OFFICER_REJECTED").length;
  const rejectionRate = total > 0 ? Math.round((rejected / total) * 100) : 0;

  const stats = [
    { label: "Total Applications", value: total, icon: FileText, trend: "+12%", up: true, color: "text-primary" },
    { label: "Pending Review", value: pending, icon: Clock, trend: `${pending} active`, up: false, color: "text-warning" },
    { label: "Approved This Month", value: approved, icon: CheckCircle, trend: "+8%", up: true, color: "text-success" },
    { label: "Rejection Rate", value: `${rejectionRate}%`, icon: XCircle, trend: "-2%", up: false, color: "text-destructive" },
  ];

  const recent = apps.slice(0, 8);

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <h1 className="text-2xl font-bold font-display text-foreground">Dashboard</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold font-display text-foreground">Dashboard</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <Card key={s.label} className="shadow-card hover:shadow-elevated transition-shadow">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-muted-foreground">{s.label}</span>
                <s.icon className={`h-5 w-5 ${s.color}`} />
              </div>
              <p className="text-3xl font-bold text-foreground">{s.value}</p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {s.up ? <TrendingUp className="h-3 w-3 text-success" /> : <TrendingDown className="h-3 w-3 text-muted-foreground" />}
                <span className={s.up ? "text-success" : "text-muted-foreground"}>{s.trend}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="shadow-card">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="font-display">Recent Applications</CardTitle>
          <Button asChild variant="outline" size="sm"><Link to="/officer/applications">View All</Link></Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-3 font-semibold text-muted-foreground">ID</th>
                  <th className="pb-3 font-semibold text-muted-foreground">Applicant</th>
                  <th className="pb-3 font-semibold text-muted-foreground hidden sm:table-cell">Status</th>
                  <th className="pb-3 font-semibold text-muted-foreground hidden md:table-cell">AI</th>
                  <th className="pb-3 font-semibold text-muted-foreground hidden lg:table-cell">Stage</th>
                  <th className="pb-3 font-semibold text-muted-foreground hidden lg:table-cell">Date</th>
                  <th className="pb-3 font-semibold text-muted-foreground">Action</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((a) => {
                  const payload = JSON.parse(a.raw_payload || "{}");
                  const applicantName = payload.applicant_name || "N/A";
                  return (
                    <tr key={a.application_id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                      <td className="py-3 font-mono text-primary font-medium">{a.application_id}</td>
                      <td className="py-3 text-foreground">{applicantName}</td>
                      <td className="py-3 hidden sm:table-cell"><Badge className={statusColors[a.status] || "bg-muted"}>{a.status}</Badge></td>
                      <td className="py-3 hidden md:table-cell">
                        <Badge className={
                          a.ai_recommendation === "APPROVE" ? "bg-success/15 text-success" :
                          a.ai_recommendation === "REJECT" ? "bg-destructive/15 text-destructive" :
                          "bg-warning/15 text-warning-foreground"
                        }>
                          {a.ai_recommendation || "N/A"}
                        </Badge>
                      </td>
                      <td className="py-3 hidden lg:table-cell text-muted-foreground">{a.processing_stage || "Pending"}</td>
                      <td className="py-3 hidden lg:table-cell text-muted-foreground">{new Date(a.created_at).toLocaleDateString("en-IN")}</td>
                      <td className="py-3">
                        <Button asChild variant="ghost" size="sm"><Link to={`/officer/applications/${a.application_id}`}><Eye className="h-4 w-4" /></Link></Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
