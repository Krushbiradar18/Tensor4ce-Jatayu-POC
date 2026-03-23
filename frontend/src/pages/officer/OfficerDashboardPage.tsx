import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileText, Clock, CheckCircle, XCircle, TrendingUp, TrendingDown, Eye, RefreshCw } from "lucide-react";
import { getOfficerQueue } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";

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
  const { data: apps = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ["officerQueue"],
    queryFn: getOfficerQueue,
    refetchInterval: 15000, // Background poll every 15s
  });

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

  const safeParse = (str: any) => {
    if (!str) return {};
    if (typeof str === 'object') return str;
    try { return JSON.parse(str); } catch (e) { return {}; }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in p-6">
        <div className="h-8 w-48 bg-muted rounded animate-pulse mb-6" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-32 bg-muted rounded animate-pulse" />)}
        </div>
        <div className="h-64 bg-muted rounded animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold font-display text-foreground">Dashboard</h1>
        <div className="flex items-center gap-2">
          {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-primary" />}
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

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

      <Card className="shadow-card overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between border-b bg-muted/30">
          <CardTitle className="font-display">Recent Applications</CardTitle>
          <Button asChild variant="ghost" size="sm" className="hover:bg-primary/10 hover:text-primary"><Link to="/officer/applications">View All</Link></Button>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="border-b border-border text-left">
                  <th className="p-3 font-semibold text-muted-foreground">ID</th>
                  <th className="p-3 font-semibold text-muted-foreground">Applicant</th>
                  <th className="p-3 font-semibold text-muted-foreground hidden sm:table-cell">Status</th>
                  <th className="p-3 font-semibold text-muted-foreground hidden md:table-cell">AI Recommendation</th>
                  <th className="p-3 font-semibold text-muted-foreground hidden lg:table-cell">Current Stage</th>
                  <th className="p-3 font-semibold text-muted-foreground">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recent.map((a) => {
                  const payload = safeParse(a.raw_payload);
                  const applicantName = payload.applicant_name || "N/A";
                  return (
                    <tr key={a.application_id} className="hover:bg-muted/30 transition-colors group">
                      <td className="p-3 font-mono text-primary font-bold">{a.application_id}</td>
                      <td className="p-3 text-foreground font-medium">{applicantName}</td>
                      <td className="p-3 hidden sm:table-cell"><Badge className={statusColors[a.status] || "bg-muted"}>{a.status}</Badge></td>
                      <td className="p-3 hidden md:table-cell">
                        <Badge variant="outline" className={
                          a.ai_recommendation === "APPROVE" ? "border-success text-success bg-success/5" :
                          a.ai_recommendation === "REJECT" ? "border-destructive text-destructive bg-destructive/5" :
                          "border-warning text-warning bg-warning/5"
                        }>
                          {a.ai_recommendation || "N/A"}
                        </Badge>
                      </td>
                      <td className="p-3 hidden lg:table-cell text-muted-foreground">{a.processing_stage || "Queued"}</td>
                      <td className="p-3">
                        <Button asChild variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 transition-opacity"><Link to={`/officer/applications/${a.application_id}`}><Eye className="h-4 w-4 mr-2" /> View</Link></Button>
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
