import PublicLayout from "@/components/PublicLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Phone, Mail, MapPin } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function ContactPage() {
  const { toast } = useToast();
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast({ title: "Inquiry Received", description: "An intelligence agent will review your request and contact you within 4 hours." });
  };

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-24 max-w-5xl">
        <h1 className="text-4xl md:text-5xl font-bold font-display text-foreground mb-12 text-center tracking-tight">Intelligence Support</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
          <Card className="shadow-lg border-primary/10">
            <CardHeader><CardTitle className="font-display text-2xl">Connect with ARIA</CardTitle></CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2"><Label>Full Name</Label><Input placeholder="John Doe" required className="h-11" /></div>
                <div className="space-y-2"><Label>Institutional Email</Label><Input type="email" placeholder="john@institution.com" required className="h-11" /></div>
                <div className="space-y-2"><Label>Inquiry Details</Label><Textarea placeholder="How can ARIA assist your risk management today?" required className="min-h-[120px]" /></div>
                <Button type="submit" className="w-full h-12 bg-accent-gradient text-primary-foreground font-semibold text-base hover:scale-[1.02] transition-transform">Dispatch Inquiry</Button>
              </form>
            </CardContent>
          </Card>
          <div className="space-y-10 py-4">
            {[
              { icon: Phone, title: "Global Intelligence Line", desc: "+1 (800) ARIA-RISK\nSupport available 24/7 for Enterprise partners" },
              { icon: Mail, title: "Electronic Correspondence", desc: "intelligence@aria.ai\npartnerships@aria.ai" },
              { icon: MapPin, title: "Risk Command Center", desc: "ARIA Intelligence Hub\nTech District, Level 42\nMumbai, MS 400051" },
            ].map((c) => (
              <div key={c.title} className="flex gap-6 group">
                <div className="w-14 h-14 bg-primary/5 rounded-2xl flex items-center justify-center shrink-0 group-hover:bg-accent-gradient group-hover:text-primary-foreground transition-all">
                  <c.icon className="h-6 w-6 text-primary group-hover:text-inherit" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-foreground mb-1 font-display">{c.title}</h3>
                  <p className="text-sm text-muted-foreground whitespace-pre-line leading-relaxed">{c.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </PublicLayout>
  );
}
