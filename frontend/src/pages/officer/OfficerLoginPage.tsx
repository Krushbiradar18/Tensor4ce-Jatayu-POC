import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ShieldCheck, Eye, EyeOff } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

import { loginOfficer } from "@/lib/api";

export default function OfficerLoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const getHomePath = (role?: string) => {
    const normalized = String(role || "officer").toLowerCase();
    if (normalized === "admin") return "/admin/dashboard";
    if (normalized === "senior_officer") return "/senior-officer/dashboard";
    return "/officer/dashboard";
  };

  useEffect(() => {
    const auth = JSON.parse(localStorage.getItem("officer_auth") || "null");
    if (auth && (auth.email || auth.username)) {
      navigate(getHomePath(auth.role), { replace: true });
    }
  }, [navigate]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      toast({ title: "Error", description: "Please enter both username and password.", variant: "destructive" });
      return;
    }

    setLoading(true);
    try {
      const response = await loginOfficer({ username, password });
      if (response.success) {
        localStorage.setItem("officer_auth", JSON.stringify(response.user));
        if (response.token) {
          localStorage.setItem("officer_token", response.token);
        }
        
        toast({ title: "Portal Initialized", description: `Access granted for ${response.user.name}` });
        navigate(getHomePath(response.user.role));
      }
    } catch (err: any) {
      toast({
        title: "Access Denied",
        description: err.message || "Intelligence credentials invalid.",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')] pointer-events-none"></div>
      
      {/* Background decorative elements */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none"></div>
      <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-accent/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2 pointer-events-none"></div>

      <Card className="w-full max-w-md shadow-elevated animate-fade-in border-border/50 relative z-10 bg-card">
        <CardHeader className="text-center pb-2 pt-8">
          <div className="relative group mx-auto mb-6">
            <div className="absolute -inset-1.5 bg-gradient-to-r from-primary to-accent rounded-2xl blur opacity-25 group-hover:opacity-40 transition duration-1000 group-hover:duration-200"></div>
            <div className="relative w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center border border-primary/20 shadow-sm transition-transform duration-500 group-hover:scale-105">
              <ShieldCheck className="h-11 w-11 text-primary animate-pulse" />
            </div>
          </div>
          <CardTitle className="text-3xl font-black font-display tracking-tight text-foreground uppercase">
            ARIA <span className="text-primary italic">AI</span>
          </CardTitle>
          <div className="flex flex-col items-center gap-1 mt-1">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em] leading-none">
              Secure Access Portal
            </span>
            <CardDescription className="text-muted-foreground mt-2 text-sm font-medium">
              Enter credentials to initialize agentic dashboard
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-6 pt-4">
            <div className="space-y-2">
              <Label className="text-foreground/80 font-medium">Username</Label>
              <Input 
                type="text" 
                value={username} 
                onChange={(e) => setUsername(e.target.value)} 
                placeholder="admin / officer1 / so1" 
                className="h-11 border-border focus-visible:ring-primary/20" 
              />
            </div>
            <div className="space-y-2">
              <Label className="text-foreground/80 font-medium">Password</Label>
              <div className="relative">
                <Input 
                  type={showPwd ? "text" : "password"} 
                  value={password} 
                  onChange={(e) => setPassword(e.target.value)} 
                  placeholder="••••••••" 
                  className="h-11 border-border focus-visible:ring-primary/20" 
                />
                <button 
                  type="button" 
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary transition-colors focus:outline-none" 
                  onClick={() => setShowPwd(!showPwd)}
                >
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Checkbox id="remember" checked={remember} onCheckedChange={(v) => setRemember(!!v)} />
                <label htmlFor="remember" className="text-sm text-muted-foreground cursor-pointer hover:text-foreground transition-colors">Remember Me</label>
              </div>
              <button type="button" className="text-sm text-primary hover:underline font-semibold">Forgot Password?</button>
            </div>
            <Button 
              type="submit" 
              className="w-full h-12 bg-primary text-primary-foreground font-bold text-base hover:opacity-90 shadow-md transition-all" 
              disabled={loading}
            >
              {loading ? "Signing In..." : "Sign In"}
            </Button>
          </form>
          <div className="mt-8 pt-6 border-t border-border/50">
            <p className="text-[10px] text-muted-foreground text-center uppercase tracking-widest leading-loose font-medium opacity-60">
              Authorized personnel only. <br/>All access attempts are monitored.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
