import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOfficerQueue } from "@/lib/api";
import { RefreshCw, BarChart3, PieChart, TrendingUp, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";

export default function OfficerAnalyticsPage() {
  const { data: apps = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ["officerQueue"],
    queryFn: getOfficerQueue,
    refetchInterval: 30000, // Analytics refresh every 30s is enough
  });

  const stats = useMemo(() => {
    const total = apps.length;
    const approved = apps.filter((a) => a.status === "OFFICER_APPROVED").length;
    const rejected = apps.filter((a) => a.status === "OFFICER_REJECTED").length;
    const pending = apps.filter((a) => !a.status.startsWith("OFFICER_")).length;

    const typeStats: Record<string, { count: number; amount: number }> = {
      "PERSONAL": { count: 0, amount: 0 },
      "HOME": { count: 0, amount: 0 },
      "AUTO": { count: 0, amount: 0 },
      "BUSINESS": { count: 0, amount: 0 },
    };

    apps.forEach((a) => {
      const type = (a.loan_purpose || "PERSONAL").toUpperCase();
      if (!typeStats[type]) typeStats[type] = { count: 0, amount: 0 };
      typeStats[type].count += 1;
      typeStats[type].amount += Number(a.loan_amount) || 0;
    });

    const totalAmount = apps.reduce((s, a) => s + (Number(a.loan_amount) || 0), 0);
    const avgAmount = total > 0 ? Math.round(totalAmount / total) : 0;

    return { total, approved, rejected, pending, typeStats, avgAmount, totalAmount };
  }, [apps]);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in p-6">
        <div className="h-8 w-64 bg-muted rounded animate-pulse mb-6" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-32 bg-muted rounded animate-pulse" />)}
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
        <h1 className="text-2xl font-bold font-display text-foregroundTracking tracking-tight">Analytics & Strategic Reports</h1>
        <div className="flex items-center gap-2">
           {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-primary mr-2" />}
           <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
             <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
             Refresh Insights
           </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard title="Approval Rate" value={`${stats.total > 0 ? Math.round((stats.approved / stats.total) * 100) : 0}%`} sub={`${stats.approved} approved`} icon={TrendingUp} color="text-success" />
        <MetricCard title="Rejection Rate" value={`${stats.total > 0 ? Math.round((stats.rejected / stats.total) * 100) : 0}%`} sub={`${stats.rejected} rejected`} icon={BarChart3} color="text-destructive" />
        <MetricCard title="Pending Review" value={String(stats.pending)} sub="Active in queue" icon={Users} color="text-warning" />
        <MetricCard title="Avg. Loan Size" value={`₹${stats.avgAmount.toLocaleString()}`} sub={`Total: ₹${(stats.totalAmount/10000000).toFixed(2)} Cr`} icon={PieChart} color="text-primary" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="shadow-card border-none bg-card/50 backdrop-blur-sm shadow-elevated">
          <CardHeader><CardTitle className="font-display flex items-center gap-2"><PieChart className="h-5 w-5 text-primary" /> Portfolio Distribution</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-6">
              {Object.entries(stats.typeStats).map(([type, data]) => (
                <div key={type} className="group cursor-help">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-foreground font-semibold group-hover:text-primary transition-colors">{type}</span>
                    <span className="text-muted-foreground">{data.count} applications • ₹{(data.amount/100000).toFixed(1)} L</span>
                  </div>
                  <div className="w-full bg-muted/50 rounded-full h-2.5 overflow-hidden">
                    <div 
                      className="bg-primary h-full transition-all duration-1000 ease-in-out" 
                      style={{ width: `${stats.total > 0 ? (data.count / stats.total) * 100 : 0}%` }} 
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-card border-none bg-card/50 backdrop-blur-sm shadow-elevated overflow-hidden">
           <div className="absolute top-0 right-0 p-8 opacity-5">
             <BarChart3 className="w-32 h-32" />
           </div>
          <CardHeader><CardTitle className="font-display">Strategic Intelligence</CardTitle></CardHeader>
          <CardContent className="space-y-5 relative z-10">
            <div className="p-4 bg-primary/5 border border-primary/20 rounded-xl hover:bg-primary/10 transition-all">
              <h4 className="text-sm font-semibold text-primary flex items-center gap-2 mb-2"><TrendingUp className="h-4 w-4" /> Portfolio Exposure</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Highest concentration is currently in <b>{Object.entries(stats.typeStats).sort((a,b)=>b[1].count - a[1].count)[0][0]}</b> segment. 
                Maintain vigilance on market volatility impacts for this sector.
              </p>
            </div>
            <div className="p-4 bg-warning/5 border border-warning/20 rounded-xl hover:bg-warning/10 transition-all">
              <h4 className="text-sm font-semibold text-warning-foreground flex items-center gap-2 mb-2"><BarChart3 className="h-4 w-4" /> Flow Velocity</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <b>{stats.pending}</b> applications are pending final officer review. 
                Turnaround Time (TAT) is reflecting optimization since the last cycle.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
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
