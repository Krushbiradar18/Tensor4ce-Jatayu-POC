import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search } from "lucide-react";
import { getApplicationStatus } from "@/lib/api";

const statusColors: Record<string, string> = {
  "PENDING": "bg-info text-info-foreground",
  "DIL_PROCESSING": "bg-info text-info-foreground",
  "AGENTS_RUNNING": "bg-warning/20 text-warning-foreground border border-warning/30",
  "DECIDED_PENDING_OFFICER": "bg-warning/20 text-warning-foreground border border-warning/30",
  "OFFICER_APPROVED": "bg-success/15 text-success border border-success/30",
  "OFFICER_REJECTED": "bg-destructive/15 text-destructive border border-destructive/30",
  "OFFICER_CONDITIONAL": "bg-accent/20 text-accent-foreground border border-accent/30",
  "OFFICER_ESCALATED": "bg-accent/20 text-accent-foreground border border-accent/30",
  "ERROR": "bg-destructive/15 text-destructive border border-destructive/30",
};

export default function TrackPage() {
  const [params] = useSearchParams();
  const [searchId, setSearchId] = useState(params.get("id") || "");
  const [app, setApp] = useState<any>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
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

  const displayStatus = app 
    ? (["DIL_PROCESSING", "AGENTS_RUNNING", "DECIDED_PENDING_OFFICER"].includes(app.status) ? "PENDING" : app.status)
    : "";

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-12 max-w-2xl">
        <h1 className="text-3xl font-bold font-display text-foreground mb-2 text-center">Track Your Application</h1>
        <p className="text-muted-foreground text-center mb-8">Enter your Application ID to check the current status</p>

        <div className="flex gap-3 mb-8">
          <Input value={searchId} onChange={(e) => setSearchId(e.target.value)} placeholder="Enter Application ID (e.g., APP-12345678)"
            onKeyDown={(e) => e.key === "Enter" && handleSearch()} className="flex-1" />
          <Button onClick={handleSearch} disabled={loading}><Search className="mr-2 h-4 w-4" /> {loading ? "Searching..." : "Search"}</Button>
        </div>

        {notFound && (
          <div className="bg-destructive/10 text-destructive rounded-lg p-4 text-center text-sm">
            No application found with ID "{searchId}". Please check and try again.
          </div>
        )}

        {app && (
          <Card className="shadow-elevated animate-fade-in">
            <CardHeader>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="font-display">Application {app.application_id}</CardTitle>
                <Badge className={statusColors[displayStatus] || "bg-muted"}>{displayStatus}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                <InfoRow label="Application ID" value={app.application_id} />
                <InfoRow label="Status" value={displayStatus} />
                {app.message && <InfoRow label="Message" value={app.message} />}
                {app.officer_decision && <InfoRow label="Officer Decision" value={app.officer_decision} />}
                {app.officer_reason && <InfoRow label="Officer Reason" value={app.officer_reason} />}
              </div>
              {app.officer_decision && (
                <div className="bg-muted rounded-lg p-4 text-sm">
                  <p className="font-semibold text-foreground mb-1">Decision Status</p>
                  <p className="text-muted-foreground">{app.officer_decision === "APPROVED" ? "Your application has been approved!" : app.officer_decision === "REJECTED" ? "Your application has been rejected." : "Your application is under review."}</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </PublicLayout>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground font-medium">{value}</span>
    </div>
  );
}
