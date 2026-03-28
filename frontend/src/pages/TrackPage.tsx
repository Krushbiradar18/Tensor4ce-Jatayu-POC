import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, Loader2, Activity, ShieldCheck, CheckCircle2 } from "lucide-react";
import { getApplicationStatus } from "@/lib/api";

const statusColors: Record<string, string> = {
  "PENDING": "bg-primary/10 text-primary border-primary/20",
  "DIL_PROCESSING": "bg-primary/10 text-primary border-primary/20",
  "AGENTS_RUNNING": "bg-accent/10 text-accent border-accent/20 animate-pulse",
  "DECIDED_PENDING_OFFICER": "bg-accent/10 text-accent border-accent/20",
  "OFFICER_APPROVED": "bg-success/10 text-success border-success/20",
  "OFFICER_REJECTED": "bg-destructive/10 text-destructive border-destructive/20",
  "OFFICER_CONDITIONAL": "bg-warning/10 text-warning border-warning/20",
  "OFFICER_ESCALATED": "bg-warning/10 text-warning border-warning/20",
};

export default function TrackPage() {
  const [params] = useSearchParams();
  const [searchId, setSearchId] = useState(params.get("id") || "");
  const [app, setApp] = useState<any>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!searchId.trim()) return;
    setLoading(true);
    setNotFound(false);
    setApp(null);

    try {
      const result = await getApplicationStatus(searchId.trim());
      setApp(result);
    } catch (error) {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  };

  const currentStatus = app?.status || "PENDING";
  const displayStatus = (["DIL_PROCESSING", "AGENTS_RUNNING", "DECIDED_PENDING_OFFICER"].includes(currentStatus)) 
    ? "PROCESSING" 
    : currentStatus.replace("OFFICER_", "");

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-24 max-w-3xl">
        <div className="text-center mb-12">
          <h1 className="text-4xl md:text-5xl font-bold font-display text-foreground mb-4 tracking-tight">Track Application</h1>
          <p className="text-muted-foreground text-lg font-light">Enter your application reference ID to check the current status.</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 mb-12">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <Input 
              value={searchId} 
              onChange={(e) => setSearchId(e.target.value)} 
              placeholder="e.g. APP-8273"
              onKeyDown={(e) => e.key === "Enter" && handleSearch()} 
              className="h-14 pl-12 bg-background/50 border-primary/10 transition-all focus:border-primary/40 text-lg" 
            />
          </div>
          <Button onClick={handleSearch} disabled={loading || !searchId} className="h-14 px-8 bg-accent-gradient text-primary-foreground font-bold text-lg shadow-xl hover:scale-105 transition-all">
            {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Track Status"}
          </Button>
        </div>

        {notFound && (
          <div className="bg-destructive/5 text-destructive border border-destructive/20 rounded-2xl p-6 text-center animate-fade-in group">
             <Activity className="h-10 w-10 mx-auto mb-3 opacity-50 group-hover:scale-110 transition-transform" />
             <p className="font-bold text-lg">Application Not Found</p>
             <p className="text-sm opacity-80 mt-1">Unable to locate application "{searchId}". Please check the ID and try again.</p>
          </div>
        )}

        {app && (
          <Card className="shadow-2xl animate-fade-in glass border-primary/5 overflow-hidden">
            <div className="h-2 bg-accent-gradient w-full"></div>
            <CardHeader className="pb-8">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/5 flex items-center justify-center">
                    <CheckCircle2 className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle className="font-display text-2xl">Application Details</CardTitle>
                </div>
                <Badge variant="outline" className={`${statusColors[currentStatus] || "bg-muted"} px-4 py-1.5 rounded-full font-bold uppercase tracking-widest text-xs`}>
                  {displayStatus}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-8">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-8 text-sm">
                <div className="space-y-1">
                  <p className="text-muted-foreground font-medium uppercase tracking-tight text-[10px]">Reference Number</p>
                  <p className="text-xl font-mono font-bold text-foreground">{app.application_id}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground font-medium uppercase tracking-tight text-[10px]">Current Status</p>
                  <p className="text-xl font-bold text-foreground">{displayStatus}</p>
                </div>
              </div>

              {app.officer_decision && (
                <div className="bg-primary/5 rounded-2xl p-6 border border-primary/10 relative overflow-hidden group">
                  <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <ShieldCheck className="h-16 w-16" />
                  </div>
                  <h4 className="text-lg font-bold text-foreground mb-2 flex items-center gap-2">
                     Application Status
                  </h4>
                  <p className="text-muted-foreground leading-relaxed">
                    {app.officer_decision === "APPROVED" 
                      ? "Your application has been approved. Our team will contact you soon with the next steps." 
                      : app.officer_decision === "REJECTED" 
                        ? "We regret to inform you that your application was not successful at this time." 
                        : "Your application is currently under manual review by our credit officers."}
                  </p>
                  {app.officer_reason && (
                    <div className="mt-4 pt-4 border-t border-primary/10">
                       <p className="text-xs font-bold text-primary mb-1 uppercase tracking-widest">Bank Remarks</p>
                       <p className="text-sm italic text-muted-foreground">"{app.officer_reason}"</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </PublicLayout>
  );
}
