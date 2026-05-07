import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOfficerQueue } from "@/lib/api";
import { RefreshCw, BarChart3, PieChart, TrendingUp, Users, AlertCircle, CheckCircle2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";

export default function SeniorOfficerAnalyticsPage() {
  const auth = JSON.parse(localStorage.getItem("officer_auth") || "null");
  
  const { data: apps = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ["officerQueue"],
    queryFn: getOfficerQueue,
    refetchInterval: 30000,
  });

  const stats = useMemo(() => {
    // Filter apps escalated to this senior officer
    const escalatedToMe = apps.filter((a) => a.escalated_to_senior_officer_id === auth?.id);
    
    const total = escalatedToMe.length;
    const approved = escalatedToMe.filter((a) => a.status === "OFFICER_APPROVED").length;
    const rejected = escalatedToMe.filter((a) => a.status === "OFFICER_REJECTED").length;
    const conditional = escalatedToMe.filter((a) => a.status === "OFFICER_CONDITIONAL").length;
    const pending = escalatedToMe.filter((a) => a.status === "OFFICER_ESCALATED").length;
    
    const resolved = approved + rejected + conditional;
    const resolutionRate = total > 0 ? Math.round((resolved / total) * 100) : 0;

    const typeStats: Record<string, { count: number; amount: number }> = {
      "PERSONAL": { count: 0, amount: 0 },
      "HOME": { count: 0, amount: 0 },
      "AUTO": { count: 0, amount: 0 },
      "BUSINESS": { count: 0, amount: 0 },
    };

    escalatedToMe.forEach((a) => {
      const type = (a.loan_purpose || "PERSONAL").toUpperCase();
      if (!typeStats[type]) typeStats[type] = { count: 0, amount: 0 };
      typeStats[type].count += 1;
      typeStats[type].amount += Number(a.loan_amount) || 0;
    });

    const totalAmount = escalatedToMe.reduce((s, a) => s + (Number(a.loan_amount) || 0), 0);
    const avgAmount = total > 0 ? Math.round(totalAmount / total) : 0;

    return { 
      total, 
      approved, 
      rejected, 
      conditional,
      pending, 
      resolved,
      resolutionRate,
      typeStats, 
      avgAmount, 
      totalAmount 
    };
  }, [apps, auth?.id]);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in p-6">
        <div className="h-8 w-64 bg-muted rounded animate-pulse mb-6" />
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-32 bg-muted rounded animate-pulse" />)}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
           <div className="h-64 bg-muted rounded animate-pulse" />
           <div className="h-64 bg-muted rounded animate-pulse" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black font-display text-foreground tracking-tight uppercase">Analytics</h1>
          <p className="text-[10px] text-muted-foreground mt-1 uppercase tracking-[0.2em] font-bold flex items-center gap-2 opacity-80">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-40"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary shadow-[0_0_8px_hsl(var(--primary))]"></span>
            </span>
            Escalated Applications Performance
          </p>
        </div>
        <div className="flex items-center gap-2">
           {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-primary mr-2" />}
           <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
             <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
             Refresh Insights
           </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard 
          title="Total Assigned" 
          value={String(stats.total)} 
          sub="escalations to you" 
          icon={Users} 
          color="text-blue-600" 
        />
        <MetricCard 
          title="Resolution Rate" 
          value={`${stats.resolutionRate}%`}
          sub={`${stats.resolved} resolved`} 
          icon={TrendingUp} 
          color="text-success" 
        />
        <MetricCard 
          title="Approved" 
          value={String(stats.approved)} 
          sub={`${stats.total > 0 ? Math.round((stats.approved / stats.total) * 100) : 0}% of total`}
          icon={CheckCircle2} 
          color="text-success" 
        />
        <MetricCard 
          title="Rejected" 
          value={String(stats.rejected)} 
          sub={`${stats.total > 0 ? Math.round((stats.rejected / stats.total) * 100) : 0}% of total`}
          icon={AlertCircle} 
          color="text-destructive" 
        />
        <MetricCard 
          title="Conditional" 
          value={String(stats.conditional)} 
          sub="pending final action" 
          icon={BarChart3} 
          color="text-warning" 
        />
      </div>

      {stats.pending > 0 && (
        <Card className="shadow-card border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-950/30">
          <CardContent className="p-4 flex items-start gap-4">
            <div className="p-3 rounded-lg bg-amber-100 dark:bg-amber-900">
              <AlertCircle className="h-6 w-6 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-amber-900 dark:text-amber-100 mb-1">Pending Review</h3>
              <p className="text-sm text-amber-800 dark:text-amber-200">
                You have <b>{stats.pending}</b> application{stats.pending !== 1 ? 's' : ''} pending your review. 
                Prompt action helps maintain optimal SLA compliance and applicant satisfaction.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="shadow-card border-none bg-card/50 backdrop-blur-sm shadow-elevated">
          <CardHeader><CardTitle className="font-display flex items-center gap-2"><PieChart className="h-5 w-5 text-primary" /> Loan Type Distribution</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-6">
              {Object.entries(stats.typeStats).map(([type, data]) => {
                const percentage = stats.total > 0 ? (data.count / stats.total) * 100 : 0;
                return (
                  <div key={type} className="group cursor-help">
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-foreground font-semibold group-hover:text-primary transition-colors">{type}</span>
                      <span className="text-muted-foreground">{data.count} apps • ₹{(data.amount/100000).toFixed(1)} L</span>
                    </div>
                    <div className="w-full bg-muted/50 rounded-full h-2.5 overflow-hidden">
                      <div 
                        className="bg-primary h-full transition-all duration-1000 ease-in-out" 
                        style={{ width: `${percentage}%` }} 
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-card border-none bg-card/50 backdrop-blur-sm shadow-elevated overflow-hidden">
           <div className="absolute top-0 right-0 p-8 opacity-5">
             <BarChart3 className="w-32 h-32" />
           </div>
          <CardHeader><CardTitle className="font-display">Decision Breakdown</CardTitle></CardHeader>
          <CardContent className="space-y-5 relative z-10">
            <div className="p-4 bg-success/5 border border-success/20 rounded-xl hover:bg-success/10 transition-all">
              <h4 className="text-sm font-semibold text-success flex items-center gap-2 mb-2"><CheckCircle2 className="h-4 w-4" /> Approvals</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <b>{stats.approved}</b> applications approved. Your approval rate is strong and demonstrates confidence in the screening process.
              </p>
            </div>
            <div className="p-4 bg-destructive/5 border border-destructive/20 rounded-xl hover:bg-destructive/10 transition-all">
              <h4 className="text-sm font-semibold text-destructive flex items-center gap-2 mb-2"><AlertCircle className="h-4 w-4" /> Rejections</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <b>{stats.rejected}</b> applications rejected. Effective risk mitigation is maintaining portfolio quality.
              </p>
            </div>
            <div className="p-4 bg-warning/5 border border-warning/20 rounded-xl hover:bg-warning/10 transition-all">
              <h4 className="text-sm font-semibold text-warning-foreground flex items-center gap-2 mb-2"><BarChart3 className="h-4 w-4" /> Conditional</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <b>{stats.conditional}</b> applications pending additional info. Follow-up ensures complete documentation.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {stats.total === 0 && (
        <Card className="shadow-card border-dashed">
          <CardContent className="p-12 text-center">
            <Users className="h-12 w-12 text-muted-foreground/50 mx-auto mb-4" />
            <p className="text-muted-foreground font-medium">No applications escalated to you yet</p>
            <p className="text-sm text-muted-foreground mt-2">Check back when officers escalate applications for your review</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricCard({ title, value, sub, icon: Icon, color }: { title: string; value: string; sub: string; icon: any; color: string }) {
  return (
    <Card className="shadow-card overflow-hidden hover:shadow-elevated transition-all border-none bg-card/50 backdrop-blur-sm">
      <CardContent className="p-5 flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1 font-medium">{title}</p>
          <p className="text-3xl font-bold text-foreground tracking-tight">{value}</p>
          <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-primary/30" />
            {sub}
          </p>
        </div>
        <div className={`p-3 rounded-xl bg-muted/80 ${color} shadow-inner`}>
          <Icon className="h-6 w-6" />
        </div>
      </CardContent>
    </Card>
  );
}
