import { Link, useLocation } from "react-router-dom";
import { Building2, Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

const navLinks = [
  { to: "/", label: "Home" },
  { to: "/apply", label: "Apply" },
  { to: "/track", label: "Track" },
];

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-card border-b border-border sticky top-0 z-50">
        <div className="container mx-auto px-4 flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-hero-gradient flex items-center justify-center">
              <Building2 className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="text-xl font-bold font-display text-foreground">BankEase</span>
          </Link>
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  location.pathname === l.to ? "bg-secondary text-primary font-semibold" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                {l.label}
              </Link>
            ))}
            <Button asChild size="sm" className="ml-3 bg-gold-gradient text-accent-foreground hover:opacity-90">
              <Link to="/apply">Apply Now</Link>
            </Button>
          </nav>
          <button className="md:hidden text-foreground" onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
        {mobileOpen && (
          <div className="md:hidden border-t border-border bg-card px-4 pb-4">
            {navLinks.map((l) => (
              <Link key={l.to} to={l.to} onClick={() => setMobileOpen(false)}
                className={`block py-2 text-sm font-medium ${location.pathname === l.to ? "text-primary" : "text-muted-foreground"}`}>
                {l.label}
              </Link>
            ))}
            <Button asChild size="sm" className="mt-2 w-full bg-gold-gradient text-accent-foreground">
              <Link to="/apply" onClick={() => setMobileOpen(false)}>Apply Now</Link>
            </Button>
          </div>
        )}
      </header>
      <main className="flex-1">{children}</main>
      <footer className="bg-primary text-primary-foreground py-10">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Building2 className="h-5 w-5" />
                <span className="text-lg font-bold font-display">BankEase</span>
              </div>
              <p className="text-primary-foreground/70 text-sm">Your trusted digital banking partner for all financial needs.</p>
            </div>
            <div>
              <h4 className="font-semibold mb-3">Quick Links</h4>
              <div className="flex flex-col gap-1 text-sm text-primary-foreground/70">
                <Link to="/apply" className="hover:text-primary-foreground">Apply for Loan</Link>
                <Link to="/track" className="hover:text-primary-foreground">Track Application</Link>
              </div>
            </div>
            <div>
              <h4 className="font-semibold mb-3">Contact</h4>
              <p className="text-sm text-primary-foreground/70">support@bankease.in<br />1800-123-4567<br />Mumbai, Maharashtra</p>
            </div>
          </div>
          <div className="border-t border-primary-foreground/20 mt-8 pt-6 text-center text-sm text-primary-foreground/50">
            © {new Date().getFullYear()} BankEase. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
