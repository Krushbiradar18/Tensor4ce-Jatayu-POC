import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate, Outlet, Navigate } from "react-router-dom";
import { ShieldCheck, LayoutDashboard, FileText, BarChart3, Settings, User, LogOut, Bell, Search, Menu, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";

const navItems = [
  { to: "/officer/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/officer/applications", icon: FileText, label: "All Applications" },
  { to: "/officer/analytics", icon: BarChart3, label: "Analytics" },
  { to: "/officer/profile", icon: Settings, label: "Settings" },
];

export default function OfficerLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  
  const authStr = localStorage.getItem("officer_auth");
  const auth = authStr ? JSON.parse(authStr) : null;

  // Secondary protection layer
  useEffect(() => {
    if (!auth || !auth.email) {
      console.log("[OfficerLayout] No auth found, redirecting");
      navigate("/officer/login", { replace: true });
    }
  }, [auth, navigate]);

  if (!auth || !auth.email) {
    return null; // Don't even render shell
  }

  const handleLogout = () => {
    localStorage.removeItem("officer_auth");
    localStorage.removeItem("officer_token");
    navigate("/officer/login");
    toast({ title: "Logged Out", description: "You have been successfully logged out." });
  };

  const handleSearch = () => {
    const query = searchQuery.trim();
    if (query) {
      // Always go to the list page with the search filter
      // This ensures we show a list of matches for IDs, names, emails, etc.
      navigate(`/officer/applications?search=${encodeURIComponent(query)}`);
      setSearchQuery("");
      setSidebarOpen(false);
    }
  };

  const isActive = (path: string) => {
    if (path.includes("?")) return location.pathname + location.search === path;
    return location.pathname === path;
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-sidebar border-r border-sidebar-border transform transition-transform lg:translate-x-0 lg:static lg:inset-auto ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center gap-2 px-5 h-16 border-b border-sidebar-border">
          <div className="w-9 h-9 rounded-lg bg-sidebar-primary flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-sidebar-primary-foreground" />
          </div>
          <span className="text-xl font-bold font-display tracking-tight text-sidebar-foreground">ARIA</span>
          <button className="lg:hidden ml-auto text-sidebar-foreground" onClick={() => setSidebarOpen(false)}><X className="h-5 w-5" /></button>
        </div>
        <nav className="p-3 space-y-1">
          {navItems.map((item) => (
            <Link key={item.label} to={item.to} onClick={() => setSidebarOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive(item.to) ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-muted hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
              }`}>
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="absolute bottom-0 left-0 right-0 p-3 border-t border-sidebar-border">
          <button onClick={handleLogout} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-sidebar-muted hover:bg-sidebar-accent/50 hover:text-sidebar-foreground w-full transition-colors">
            <LogOut className="h-4 w-4" /> Logout
          </button>
        </div>
      </aside>

      {sidebarOpen && <div className="fixed inset-0 bg-foreground/30 z-40 lg:hidden" onClick={() => setSidebarOpen(false)} />}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-card border-b border-border flex items-center px-4 gap-4 sticky top-0 z-30">
          <button className="lg:hidden text-foreground" onClick={() => setSidebarOpen(true)}><Menu className="h-5 w-5" /></button>
          <div className="flex-1 flex items-center max-w-md">
            <div className="relative w-full">
              <button 
                className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground hover:text-primary transition-colors focus:outline-none"
                onClick={handleSearch}
                aria-label="Search"
              >
                <Search className="h-4 w-4" />
              </button>
              <Input 
                value={searchQuery} 
                onChange={(e) => setSearchQuery(e.target.value)} 
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="Search ID, name, or email..." 
                className="pl-9 h-10 shadow-sm focus-visible:ring-1" 
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button 
              className="flex items-center gap-2 pr-2 leading-none hover:bg-muted/50 rounded-full transition-all group"
              onClick={() => navigate("/officer/profile")}
            >
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center border border-primary/20 group-hover:border-primary/40">
                <User className="h-5 w-5 text-primary" />
              </div>
              <div className="text-left hidden sm:block">
                <p className="text-sm font-semibold text-foreground">{auth.name || "Officer"}</p>
                <p className="text-[10px] text-muted-foreground">{auth.role || "Loan Officer"}</p>
              </div>
            </button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
