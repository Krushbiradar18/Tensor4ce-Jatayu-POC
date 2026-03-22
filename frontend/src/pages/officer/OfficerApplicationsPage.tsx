import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Eye, ChevronLeft, ChevronRight, Search } from "lucide-react";
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

const PAGE_SIZE = 10;

export default function OfficerApplicationsPage() {
  const [params] = useSearchParams();
  const presetStatus = params.get("status");
  const [allApps, setAllApps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(presetStatus || "all");
  const [page, setPage] = useState(0);
  const [sortField, setSortField] = useState<"date" | "amount">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    getOfficerQueue()
      .then((data) => {
        setAllApps(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch officer queue:", err);
        setLoading(false);
      });
  }, []);

  const filtered = useMemo(() => {
    let result = allApps;
    if (statusFilter === "pending") result = result.filter((a) => a.status === "PENDING" || a.status === "DIL_PROCESSING" || a.status === "AGENTS_RUNNING" || a.status === "DECIDED_PENDING_OFFICER");
    else if (statusFilter === "approved") result = result.filter((a) => a.status === "OFFICER_APPROVED");
    else if (statusFilter === "rejected") result = result.filter((a) => a.status === "OFFICER_REJECTED");
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((a) => {
        const payload = JSON.parse(a.raw_payload || "{}");
        const applicantName = (payload.applicant_name || "").toLowerCase();
        const email = (payload.email || "").toLowerCase();
        return a.application_id.toLowerCase().includes(q) || applicantName.includes(q) || email.includes(q);
      });
    }
    result.sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortField === "date") return mul * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      const aPayload = JSON.parse(a.raw_payload || "{}");
      const bPayload = JSON.parse(b.raw_payload || "{}");
      return mul * ((aPayload.loan_amount_requested || 0) - (bPayload.loan_amount_requested || 0));
    });
    return result;
  }, [allApps, statusFilter, search, sortField, sortDir]);

  const pageCount = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <h1 className="text-2xl font-bold font-display text-foreground">Applications</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-2xl font-bold font-display text-foreground">Applications</h1>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} placeholder="Search by ID, name, email..." className="pl-9" />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
          <SelectTrigger className="w-full sm:w-44"><SelectValue placeholder="Filter status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
        <Select value={`${sortField}-${sortDir}`} onValueChange={(v) => { const [f, d] = v.split("-"); setSortField(f as any); setSortDir(d as any); }}>
          <SelectTrigger className="w-full sm:w-44"><SelectValue placeholder="Sort" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="date-desc">Newest First</SelectItem>
            <SelectItem value="date-asc">Oldest First</SelectItem>
            <SelectItem value="amount-desc">Highest Amount</SelectItem>
            <SelectItem value="amount-asc">Lowest Amount</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card className="shadow-card">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-left">
                  <th className="p-3 font-semibold text-muted-foreground">ID</th>
                  <th className="p-3 font-semibold text-muted-foreground">Applicant</th>
                  <th className="p-3 font-semibold text-muted-foreground hidden sm:table-cell">Loan Type</th>
                  <th className="p-3 font-semibold text-muted-foreground hidden md:table-cell">Amount</th>
                  <th className="p-3 font-semibold text-muted-foreground">Status</th>
                  <th className="p-3 font-semibold text-muted-foreground">AI Decision</th>
                  <th className="p-3 font-semibold text-muted-foreground hidden lg:table-cell">Date</th>
                  <th className="p-3 font-semibold text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((a) => {
                  const payload = JSON.parse(a.raw_payload || "{}");
                  const applicantName = payload.applicant_name || "N/A";
                  const email = payload.email || "";
                  const loanType = payload.loan_purpose || "N/A";
                  const loanAmount = payload.loan_amount_requested || 0;
                  return (
                    <tr key={a.application_id} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                      <td className="p-3 font-mono text-primary font-medium">{a.application_id}</td>
                      <td className="p-3">
                        <div className="text-foreground font-medium">{applicantName}</div>
                        <div className="text-xs text-muted-foreground">{email}</div>
                      </td>
                      <td className="p-3 hidden sm:table-cell text-muted-foreground">{loanType}</td>
                      <td className="p-3 hidden md:table-cell text-foreground font-medium">₹{loanAmount.toLocaleString()}</td>
                      <td className="p-3"><Badge className={statusColors[a.status] || "bg-muted"}>{a.status}</Badge></td>
                      <td className="p-3">
                        <Badge className={
                          a.ai_recommendation === "APPROVE" ? "bg-success/15 text-success" :
                          a.ai_recommendation === "REJECT" ? "bg-destructive/15 text-destructive" :
                          "bg-warning/15 text-warning-foreground"
                        }>
                          {a.ai_recommendation || "N/A"}
                        </Badge>
                      </td>
                      <td className="p-3 hidden lg:table-cell text-muted-foreground">{new Date(a.created_at).toLocaleDateString("en-IN")}</td>
                      <td className="p-3">
                        <Button asChild variant="ghost" size="sm"><Link to={`/officer/applications/${a.application_id}`}><Eye className="h-4 w-4 mr-1" /> View</Link></Button>
                      </td>
                    </tr>
                  );
                })}
                {paged.length === 0 && (
                  <tr><td colSpan={8} className="p-8 text-center text-muted-foreground">No applications found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center justify-between p-3 border-t border-border">
              <span className="text-sm text-muted-foreground">Page {page + 1} of {pageCount} ({filtered.length} total)</span>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
                <Button variant="outline" size="sm" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
