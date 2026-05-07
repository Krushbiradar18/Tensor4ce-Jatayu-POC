import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate, Outlet, Navigate } from "react-router-dom";
import { ShieldCheck, LayoutDashboard, FileText, BarChart3, Settings, User, LogOut, Search, Menu, X, ShieldAlert } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { useQuery } from "@tanstack/react-query";
import { getOfficerQueue } from "@/lib/api";

const navByRole: Record<string, Array<{ to: string; icon: any; label: string }>> = {
  admin: [
    { to: "/admin/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/admin/analytics", icon: BarChart3, label: "Analytics" },
    { to: "/admin/admin-panel", icon: ShieldAlert, label: "Admin Panel" },
  ],
  officer: [
    { to: "/officer/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/officer/applications", icon: FileText, label: "All Applications" },
    { to: "/officer/analytics", icon: BarChart3, label: "Analytics" },
    { to: "/officer/profile", icon: Settings, label: "Settings" },
  ],
  senior_officer: [
    { to: "/senior-officer/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/senior-officer/applications", icon: FileText, label: "All Applications" },
    { to: "/senior-officer/analytics", icon: BarChart3, label: "Analytics" },
  ],
};

const homeByRole: Record<string, string> = {
  admin: "/admin/dashboard",
  officer: "/officer/dashboard",
  senior_officer: "/senior-officer/dashboard",
};

const profileByRole: Record<string, string> = {
  admin: "/admin/admin-panel",
  officer: "/officer/profile",
  senior_officer: "/senior-officer/dashboard",
};

export default function OfficerLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  
  const authStr = localStorage.getItem("officer_auth");
  const auth = authStr ? JSON.parse(authStr) : null;
  const role = String(auth?.role || "officer").toLowerCase();
  const navItems = navByRole[role] || navByRole.officer;
  const homePath = homeByRole[role] || homeByRole.officer;
  const profilePath = profileByRole[role] || profileByRole.officer;

  // Fetch applications to count escalated ones (for senior officers)
  const { data: applications = [] } = useQuery({
    queryKey: ["officerQueue"],
    queryFn: getOfficerQueue,
    enabled: role === "senior_officer",
  });

  // Count only pending escalations assigned to this senior officer
  const escalatedCount = role === "senior_officer" 
    ? applications.filter(
        (app) => app.escalated_to_senior_officer_id === auth?.id && app.status === "OFFICER_ESCALATED"
      ).length 
    : 0;

  // Secondary protection layer
  useEffect(() => {
    if (!auth || (!auth.email && !auth.username)) {
      console.log("[OfficerLayout] No auth found, redirecting");
      navigate("/officer/login", { replace: true });
    }
  }, [auth, navigate]);

  if (!auth || (!auth.email && !auth.username)) {
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
      const target = role === "admin"
        ? homePath
        : role === "senior_officer"
          ? `/senior-officer/applications?search=${encodeURIComponent(query)}`
          : `/officer/applications?search=${encodeURIComponent(query)}`;
      navigate(target);
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
        <div className="flex flex-col gap-4 px-6 py-8 border-b border-sidebar-border/50 bg-sidebar-background/60 backdrop-blur-md sticky top-0 z-10 overflow-hidden">
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-primary/10 rounded-full blur-3xl pointer-events-none"></div>
          
          <div className="flex items-center justify-between">
            <div className="relative group">
              <div className="absolute -inset-1.5 bg-gradient-to-r from-primary/60 to-accent/60 rounded-2xl blur opacity-30 group-hover:opacity-60 transition duration-1000 group-hover:duration-200"></div>
              <div className="relative w-12 h-12 rounded-2xl bg-sidebar-primary flex items-center justify-center shadow-[0_0_15px_rgba(var(--sidebar-primary),0.3)] transform transition-transform group-hover:scale-110 duration-500">
                <ShieldCheck className="h-7 w-7 text-sidebar-primary-foreground" />
              </div>
            </div>
            <button className="lg:hidden text-sidebar-foreground hover:bg-sidebar-accent/50 p-1.5 rounded-lg transition-colors" onClick={() => setSidebarOpen(false)}><X className="h-5 w-5" /></button>
          </div>

          <div className="flex flex-col space-y-1">
            <span className="text-4xl font-black font-display tracking-tighter text-white uppercase leading-none bg-gradient-to-br from-white via-white to-white/50 bg-clip-text text-transparent drop-shadow-sm">
              ARIA <span className="text-primary italic">AI</span>
            </span>
            <div className="flex flex-col">
              {/* <span className="text-[8px] font-black text-primary/90 uppercase tracking-[0.25em] leading-none mb-1">
                Risk Management
              </span> */}
              <span className="text-[12px] font-bold text-sidebar-muted uppercase tracking-[0.1em] leading-none opacity-60">
                {role === "admin" ? "Administrator Console" : role === "senior_officer" ? "Senior Officer Console" : "Agentic Risk Intelligence & Analytics"}
              </span>
            </div>
          </div>
        </div>
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            // Show badge for All Applications if it's a senior officer with escalated items
            const showBadge = role === "senior_officer" && item.label === "All Applications" && escalatedCount > 0;
            
            return (
              <Link key={item.label} to={item.to} onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors relative ${
                  isActive(item.to) ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-muted hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                }`}>
                <item.icon className="h-4 w-4" />
                <div className="flex items-center gap-2 flex-1">
                  {item.label}
                  {showBadge && (
                    <span className="ml-auto inline-flex items-center justify-center h-5 w-5 rounded-full bg-red-500 text-white text-xs font-bold">
                      {escalatedCount}
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
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
          
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shadow-sm">
              <ShieldCheck className="h-5 w-5 text-white" />
            </div>
            <span className="font-display font-black tracking-tight text-foreground text-lg uppercase">ARIA <span className="text-primary">AI</span></span>
          </div>

          <div className="flex-1 flex items-center max-w-md ml-auto lg:ml-0">
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
              onClick={() => navigate(profilePath)}
            >
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center border border-primary/20 group-hover:border-primary/40">
                <User className="h-5 w-5 text-primary" />
              </div>
              <div className="text-left hidden sm:block">
                <p className="text-sm font-semibold text-foreground">{auth.name || auth.username || "Officer"}</p>
                <p className="text-[10px] text-muted-foreground">{auth.role || "officer"}</p>
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
