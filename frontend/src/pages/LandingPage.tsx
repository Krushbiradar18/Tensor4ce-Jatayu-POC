import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ShieldCheck, Cpu, Brain, Zap, ArrowRight, Building2, TrendingUp, Users } from "lucide-react";
import PublicLayout from "@/components/PublicLayout";
import { Badge } from "@/components/ui/badge";

const features = [
  { icon: Cpu, title: "Smart Approvals", desc: "Advanced processing for lightning-fast credit decisions." },
  { icon: ShieldCheck, title: "Bank-Grade security", desc: "Multi-layered verification to keep your data safe and secure." },
  { icon: Brain, title: "Personalized Rates", desc: "Competitive interest rates tailored to your financial profile." },
];

const loanTypes = [
  { icon: Users, title: "Personal Loan", desc: "For your personal needs and emergencies", available: true },
  { icon: Building2, title: "Home Loan", desc: "Make your dream home a reality", available: false },
  { icon: TrendingUp, title: "Business Loan", desc: "Fuel your business growth and expansion", available: false },
];

export default function LandingPage() {
  return (
    <PublicLayout>
      {/* Hero */}
      <section className="bg-hero-gradient py-24 md:py-40 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] pointer-events-none"></div>
        <div className="container mx-auto px-4 text-center relative z-10">
          <Badge variant="outline" className="mb-6 px-4 py-1 text-primary-foreground border-primary-foreground/20 bg-primary-foreground/5 animate-fade-in">
            New: Instant Personal Loans Now Available
          </Badge>
          <h1 className="text-5xl md:text-7xl font-extrabold text-primary-foreground mb-8 font-display leading-[1.1]">
            Modern Finance<br />
            <span className="text-gradient">For Everyone</span>
          </h1>
          <p className="text-xl md:text-2xl text-primary-foreground/80 max-w-3xl mx-auto mb-12 font-body font-light leading-relaxed">
            Experience the future of digital banking with ARIA. 
            Fast, secure, and transparent loan approvals in minutes.
          </p>
          <div className="flex flex-col sm:flex-row gap-6 justify-center items-center">
            <Button asChild size="lg" className="bg-accent-gradient text-primary-foreground font-semibold text-lg px-10 py-7 hover:scale-105 transition-all shadow-xl">
              <Link to="/apply">Apply for a Loan <ArrowRight className="ml-2 h-5 w-5" /></Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="text-primary-foreground border-primary-foreground/20 hover:bg-primary-foreground/10 px-10 py-7 text-lg">
              <Link to="/track">Track Application</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 md:py-32">
        <div className="container mx-auto px-4">
          <h2 className="text-4xl md:text-5xl font-bold text-center mb-16 font-display text-foreground tracking-tight">Financial Services</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {features.map((f) => (
              <div key={f.title} className="bg-card rounded-lg p-8 shadow-card hover:shadow-elevated transition-shadow text-center animate-fade-in">
                <div className="w-16 h-16 rounded-2xl bg-primary/5 flex items-center justify-center mx-auto mb-6 group-hover:bg-accent-gradient group-hover:text-primary-foreground transition-all duration-300">
                  <f.icon className="h-8 w-8 text-primary group-hover:text-inherit" />
                </div>
                <h3 className="text-2xl font-bold mb-4 font-display text-foreground">{f.title}</h3>
                <p className="text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Loan Types */}
      <section className="py-24 bg-muted/30">
        <div className="container mx-auto px-4">
          <h2 className="text-4xl md:text-5xl font-bold text-center mb-16 font-display text-foreground">Loan Products</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {loanTypes.map((l) => (
              <div key={l.title} className="bg-card rounded-lg p-8 shadow-card hover:shadow-elevated transition-all group">
                <l.icon className="h-10 w-10 text-accent mb-4" />
                <h3 className="text-xl font-semibold mb-3 font-display text-foreground">{l.title}</h3>
                <p className="text-muted-foreground mb-5">{l.desc}</p>
                {l.available ? (
                  <Button asChild variant="outline" className="group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                    <Link to="/apply">Apply Now</Link>
                  </Button>
                ) : (
                  <Button variant="outline" disabled className="cursor-not-allowed">
                    Coming Soon
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 md:py-20">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-4xl md:text-6xl font-bold mb-6 font-display text-foreground tracking-tighter">Ready to Begin?</h2>
          <p className="text-muted-foreground text-xl mb-12 max-w-2xl mx-auto font-light leading-relaxed">Join thousands of happy customers who trust ARIA for their financial needs.</p>
          <Button asChild size="lg" className="bg-accent-gradient text-primary-foreground font-semibold px-12 py-8 text-lg hover:scale-105 transition-all shadow-2xl">
            <Link to="/apply">Start Your Application <ArrowRight className="ml-2" /></Link>
          </Button>
        </div>
      </section>
    </PublicLayout>
  );
}
