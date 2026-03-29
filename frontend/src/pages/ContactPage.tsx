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
            <CardHeader><CardTitle className="font-display text-2xl">Connect with Tensor Bank</CardTitle></CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2"><Label>Full Name</Label><Input placeholder="John Doe" required className="h-11" /></div>
                <div className="space-y-2"><Label>Institutional Email</Label><Input type="email" placeholder="john@institution.com" required className="h-11" /></div>
                <div className="space-y-2"><Label>Inquiry Details</Label><Textarea placeholder="How can Tensor Bank assist your financial needs today?" required className="min-h-[120px]" /></div>
                <Button type="submit" className="w-full h-12 bg-accent-gradient text-primary-foreground font-semibold text-base hover:scale-[1.02] transition-transform">Dispatch Inquiry</Button>
              </form>
            </CardContent>
          </Card>
          <div className="space-y-8 py-4">
            <div>
              <h3 className="text-2xl font-bold text-foreground mb-4 font-display">How can we help?</h3>
              <p className="text-muted-foreground leading-relaxed mb-6">
                Whether you're looking for support with your application, have questions about our loan products, or need to speak with a representative, our team is here for you. 
              </p>
              <div className="space-y-4">
                <div className="flex items-center gap-3 text-muted-foreground">
                  <Mail className="h-5 w-5 text-primary" />
                  <span>support@tensorbank.com</span>
                </div>
                <div className="flex items-center gap-3 text-muted-foreground">
                  <Phone className="h-5 w-5 text-primary" />
                  <span>Available 24/7 for account support</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PublicLayout>
  );
}
