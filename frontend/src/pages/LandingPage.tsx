import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Shield, Clock, CheckCircle, ArrowRight, Building2, TrendingUp, Users } from "lucide-react";
import PublicLayout from "@/components/PublicLayout";

const features = [
  { icon: Clock, title: "Quick Processing", desc: "Get your loan approved within 48 hours with our streamlined process" },
  { icon: Shield, title: "100% Secure", desc: "Bank-grade encryption protects your personal and financial data" },
  { icon: CheckCircle, title: "Easy Application", desc: "Simple 4-step process with real-time guidance at every stage" },
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
      <section className="bg-hero-gradient py-20 md:py-32">
        <div className="container mx-auto px-4 text-center">
          <h1 className="text-4xl md:text-6xl font-bold text-primary-foreground mb-6 font-display">
            Your Trusted Partner in<br />
            <span className="text-gradient-gold">Financial Growth</span>
          </h1>
          <p className="text-lg md:text-xl text-primary-foreground/80 max-w-2xl mx-auto mb-10 font-body">
            Apply for loans with India's most reliable digital banking platform. Fast approvals, competitive rates, and a seamless experience.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button asChild size="lg" className="bg-gold-gradient text-accent-foreground font-semibold text-base px-8 py-6 hover:opacity-90 transition-opacity">
              <Link to="/apply">Apply Now <ArrowRight className="ml-2 h-5 w-5" /></Link>
            </Button>
            <Button asChild size="lg" className="bg-gold-gradient text-accent-foreground font-semibold text-base px-8 py-6 hover:opacity-90 transition-opacity">
              <Link to="/track">Track Application</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-16 md:py-24">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-12 font-display text-foreground">Why Choose Us</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {features.map((f) => (
              <div key={f.title} className="bg-card rounded-lg p-8 shadow-card hover:shadow-elevated transition-shadow text-center animate-fade-in">
                <div className="w-14 h-14 rounded-full bg-secondary flex items-center justify-center mx-auto mb-5">
                  <f.icon className="h-7 w-7 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-3 font-display text-foreground">{f.title}</h3>
                <p className="text-muted-foreground">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Loan Types */}
      <section className="py-16 bg-secondary/50">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-12 font-display text-foreground">Our Loan Products</h2>
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
          <h2 className="text-3xl md:text-4xl font-bold mb-4 font-display text-foreground">Ready to Get Started?</h2>
          <p className="text-muted-foreground text-lg mb-8 max-w-xl mx-auto">Join thousands of satisfied customers who trust us with their financial needs.</p>
          <Button asChild size="lg" className="bg-gold-gradient text-accent-foreground font-semibold px-10 py-6 text-base hover:opacity-90">
            <Link to="/apply">Start Your Application <ArrowRight className="ml-2" /></Link>
          </Button>
        </div>
      </section>
    </PublicLayout>
  );
}
