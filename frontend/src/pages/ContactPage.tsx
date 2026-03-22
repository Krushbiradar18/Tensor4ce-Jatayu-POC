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
    toast({ title: "Message Sent", description: "We'll get back to you within 24 hours." });
  };

  return (
    <PublicLayout>
      <div className="container mx-auto px-4 py-12 max-w-4xl">
        <h1 className="text-3xl font-bold font-display text-foreground mb-8 text-center">Contact Us</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <Card className="shadow-card">
            <CardHeader><CardTitle className="font-display">Send a Message</CardTitle></CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div><Label>Name</Label><Input placeholder="Your name" required /></div>
                <div><Label>Email</Label><Input type="email" placeholder="you@email.com" required /></div>
                <div><Label>Message</Label><Textarea placeholder="How can we help?" required /></div>
                <Button type="submit" className="w-full">Send Message</Button>
              </form>
            </CardContent>
          </Card>
          <div className="space-y-6">
            {[
              { icon: Phone, title: "Phone", desc: "1800-123-4567 (Toll Free)\nMon-Sat: 9AM - 6PM" },
              { icon: Mail, title: "Email", desc: "support@bankease.in\nloans@bankease.in" },
              { icon: MapPin, title: "Head Office", desc: "BankEase Tower, BKC\nMumbai, Maharashtra 400051" },
            ].map((c) => (
              <div key={c.title} className="flex gap-4">
                <div className="w-12 h-12 bg-secondary rounded-lg flex items-center justify-center shrink-0">
                  <c.icon className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground">{c.title}</h3>
                  <p className="text-sm text-muted-foreground whitespace-pre-line">{c.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </PublicLayout>
  );
}
