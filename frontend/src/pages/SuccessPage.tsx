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
    toast({ title: "ID Copied", description: "Application reference ID copied to clipboard." });
  };

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-24 max-w-2xl text-center animate-fade-in">
        <div className="w-24 h-24 bg-success/5 rounded-3xl flex items-center justify-center mx-auto mb-8 shadow-inner border border-success/10">
          <CheckCircle2 className="h-12 w-12 text-success" />
        </div>
        <h1 className="text-4xl md:text-5xl font-bold font-display text-foreground mb-4 tracking-tight">Application Submitted</h1>
        <p className="text-muted-foreground text-lg mb-10 font-light leading-relaxed">
          Your application has been received. Our team is now verifying your 
          details and will get back to you shortly.
        </p>

        <div className="bg-card rounded-2xl border border-primary/10 p-10 shadow-2xl mb-10 glass relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-accent-gradient"></div>
          <p className="text-sm font-bold uppercase tracking-widest text-primary/60 mb-4">Application Reference</p>
          <div className="flex items-center justify-center gap-4">
            <span className="text-3xl md:text-4xl font-bold font-mono text-foreground tracking-tighter">{id}</span>
            <button onClick={copy} className="p-2 rounded-lg bg-primary/5 text-primary hover:bg-primary/20 transition-all border border-primary/10 group">
              <Copy className="h-6 w-6 group-hover:scale-110 transition-transform" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-6 font-medium">Please save this ID to track your application status.</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-6 justify-center">
          <Button asChild size="lg" className="bg-accent-gradient text-primary-foreground font-bold h-14 px-10 shadow-xl hover:scale-105 transition-transform">
            <Link to={`/track?id=${id}`}>Track Status <ArrowRight className="ml-2 h-5 w-5" /></Link>
          </Button>
          <Button asChild size="lg" variant="outline" className="h-14 px-10 border-primary/20 hover:bg-primary/5">
            <Link to="/">Return to Home</Link>
          </Button>
        </div>
      </div>
    </PublicLayout>
  );
}
