import { useSearchParams, Link } from "react-router-dom";
import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Copy, ArrowRight } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function SuccessPage() {
  const [params] = useSearchParams();
  const id = params.get("id") || "N/A";
  const { toast } = useToast();

  const copy = () => {
    navigator.clipboard.writeText(id);
    toast({ title: "Copied!", description: "Application ID copied to clipboard." });
  };

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-20 max-w-lg text-center animate-fade-in">
        <div className="w-20 h-20 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-6">
          <CheckCircle2 className="h-12 w-12 text-success" />
        </div>
        <h1 className="text-3xl font-bold font-display text-foreground mb-3">Application Submitted!</h1>
        <p className="text-muted-foreground mb-8">Your loan application has been received and is being processed.</p>

        <div className="bg-card rounded-lg border border-border p-6 shadow-card mb-8">
          <p className="text-sm text-muted-foreground mb-2">Your Application ID</p>
          <div className="flex items-center justify-center gap-3">
            <span className="text-2xl font-bold font-mono text-primary">{id}</span>
            <button onClick={copy} className="text-muted-foreground hover:text-primary transition-colors">
              <Copy className="h-5 w-5" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-3">Please save this ID to track your application status.</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button asChild>
            <Link to={`/track?id=${id}`}>Track Application <ArrowRight className="ml-2 h-4 w-4" /></Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/">Back to Home</Link>
          </Button>
        </div>
      </div>
    </PublicLayout>
  );
}
