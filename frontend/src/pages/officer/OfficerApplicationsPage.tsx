import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Eye, ChevronLeft, ChevronRight, Search, RefreshCw } from "lucide-react";
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
  "DATA_REQUIRED": "bg-warning/15 text-warning-foreground border border-warning/20",
  "ERROR": "bg-destructive/15 text-destructive border border-destructive/20",
};

const PAGE_SIZE = 10;

export default function OfficerApplicationsPage() {
  const [params] = useSearchParams();
  const presetStatus = params.get("status");
  const presetSearch = params.get("search") || "";
  
  const [search, setSearch] = useState(presetSearch);
  const [statusFilter, setStatusFilter] = useState(presetStatus || "all");
  const [page, setPage] = useState(0);
  const [sortField, setSortField] = useState<"date" | "amount">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Sync state with URL params
  useEffect(() => {
    if (presetSearch) setSearch(presetSearch);
    if (presetStatus) setStatusFilter(presetStatus);
  }, [presetSearch, presetStatus]);


  const { data: allApps = [], isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["officerQueue"],
    queryFn: getOfficerQueue,
    refetchInterval: 15000,
  });

  const safeParse = (str: any) => {
    if (!str) return {};
    if (typeof str === 'object') return str;
    try { return JSON.parse(str); } catch (e) { return {}; }
  };

  const filtered = useMemo(() => {
    let result = [...allApps];
    if (statusFilter === "pending") result = result.filter((a) => !a.status.startsWith("OFFICER_"));
    else if (statusFilter === "approved") result = result.filter((a) => a.status === "OFFICER_APPROVED");
    else if (statusFilter === "rejected") result = result.filter((a) => a.status === "OFFICER_REJECTED");
    
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter((a) => {
        const payload = safeParse(a.raw_payload);
        const applicantName = (a.applicant_name || payload.applicant_name || "").toLowerCase();
        const email = (payload.email || "").toLowerCase();
        const loanPurpose = (a.loan_purpose || payload.loan_purpose || "").toLowerCase();
        const id = (a.application_id || "").toLowerCase();
        const fullPayload = (a.raw_payload || "").toLowerCase();
        
        return id.includes(q) || applicantName.includes(q) || email.includes(q) || loanPurpose.includes(q) || fullPayload.includes(q);
      });
    }
    
    result.sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortField === "date") return mul * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      const aPayload = safeParse(a.raw_payload);
      const bPayload = safeParse(b.raw_payload);
      return mul * ((aPayload.loan_amount_requested || 0) - (bPayload.loan_amount_requested || 0));
    });
    return result;
  }, [allApps, statusFilter, search, sortField, sortDir]);

  const pageCount = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);



  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in p-6">
        <h1 className="text-2xl font-bold font-display text-foreground">Applications</h1>
        <div className="h-10 bg-muted rounded animate-pulse" />
        <div className="h-96 bg-muted rounded animate-pulse" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-10 text-center space-y-4 rounded-xl border border-dashed mt-10">
        <div className="text-destructive font-bold text-lg">Failed to sync applications</div>
        <p className="text-muted-foreground text-sm">The backend might be busy or unreachable. Please try again.</p>
        <Button onClick={() => refetch()} variant="outline"><RefreshCw className="mr-2 h-4 w-4" /> Retry Connection</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black font-display text-foreground tracking-tight uppercase">Applications</h1>
          <p className="text-[10px] text-muted-foreground mt-1 uppercase tracking-[0.2em] font-bold flex items-center gap-2 opacity-80">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-40"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary shadow-[0_0_8px_hsl(var(--primary))]"></span>
            </span>
            ARIA AI Risk Queue Access
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-primary" />}
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} placeholder="Search by ID, name, email..." className="pl-9 h-10 shadow-sm" />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
          <SelectTrigger className="w-full sm:w-44 h-10"><SelectValue placeholder="Filter status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
        <Select value={`${sortField}-${sortDir}`} onValueChange={(v) => { const [f, d] = v.split("-"); setSortField(f as any); setSortDir(d as any); }}>
          <SelectTrigger className="w-full sm:w-44 h-10"><SelectValue placeholder="Sort" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="date-desc">Newest First</SelectItem>
            <SelectItem value="date-asc">Oldest First</SelectItem>
            <SelectItem value="amount-desc">Highest Amount</SelectItem>
            <SelectItem value="amount-asc">Lowest Amount</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card className="shadow-card border-border overflow-hidden">
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
                  <th className="p-3 font-semibold text-muted-foreground">AI Recommendation</th>
                  <th className="p-3 font-semibold text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paged.map((a) => {
                  const payload = safeParse(a.raw_payload);
                  const applicantName = payload.applicant_name || "—";
                  const email = payload.email || "";
                  const loanType = payload.loan_purpose || "—";
                  const loanAmount = payload.loan_amount_requested || 0;
                  return (
                    <tr key={a.application_id} className="hover:bg-muted/10 transition-colors group">
                      <td className="p-3 font-mono text-primary font-bold">{a.application_id}</td>
                      <td className="p-3">
                        <div className="text-foreground font-semibold">{applicantName}</div>
                        <div className="text-xs text-muted-foreground truncate max-w-[150px]">{email}</div>
                      </td>
                      <td className="p-3 hidden sm:table-cell text-muted-foreground capitalize">{loanType.toLowerCase()}</td>
                      <td className="p-3 hidden md:table-cell text-foreground font-semibold">₹{loanAmount.toLocaleString()}</td>
                      <td className="p-3"><Badge className={statusColors[a.status] || "bg-muted"}>{a.status}</Badge></td>
                      <td className="p-3">
                        <Badge variant="outline" className={
                          a.ai_recommendation === "APPROVE" ? "border-success text-success bg-success/5" :
                          a.ai_recommendation === "REJECT" ? "border-destructive text-destructive bg-destructive/5" :
                          "border-warning text-warning bg-warning/5"
                        }>
                          {a.ai_recommendation || "N/A"}
                        </Badge>
                      </td>
                      <td className="p-3">
                        <Button asChild variant="ghost" size="sm" className="hover:bg-primary/10 hover:text-primary"><Link to={`/officer/applications/${a.application_id}`}><Eye className="h-4 w-4 mr-2" /> Detail</Link></Button>
                      </td>
                    </tr>
                  );
                })}
                {paged.length === 0 && (
                  <tr><td colSpan={8} className="p-20 text-center text-muted-foreground font-medium">No results found for your search.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center justify-between p-4 border-t border-border bg-muted/20">
              <span className="text-sm text-muted-foreground">Showing <b>{page * PAGE_SIZE + 1}</b> to <b>{Math.min((page + 1) * PAGE_SIZE, filtered.length)}</b> of <b>{filtered.length}</b> applications</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4 mr-1" /> Prev</Button>
                <Button variant="outline" size="sm" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}>Next <ChevronRight className="h-4 w-4 ml-1" /></Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
