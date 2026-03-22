import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Building2, Eye, EyeOff } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function OfficerLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast({ title: "Error", description: "Please enter both email and password.", variant: "destructive" });
      return;
    }

    // Check hardcoded credentials
    if (email !== "admin" || password !== "admin123") {
      toast({
        title: "Authentication Failed",
        description: "Invalid username or password. Use admin/admin123.",
        variant: "destructive"
      });
      return;
    }

    setLoading(true);
    setTimeout(() => {
      localStorage.setItem("officer_auth", JSON.stringify({ email, name: "Admin Officer", role: "Loan Officer" }));
      navigate("/officer/dashboard");
    }, 800);
  };

  return (
    <div className="min-h-screen bg-hero-gradient flex items-center justify-center p-4">
      <Card className="w-full max-w-md shadow-elevated animate-fade-in">
        <CardHeader className="text-center pb-2">
          <div className="w-14 h-14 rounded-xl bg-hero-gradient flex items-center justify-center mx-auto mb-3">
            <Building2 className="h-8 w-8 text-primary-foreground" />
          </div>
          <CardTitle className="text-2xl font-display">BankEase Officer Portal</CardTitle>
          <CardDescription>Sign in to access the dashboard</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <Label>Email / Username</Label>
              <Input type="text" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin" />
            </div>
            <div>
              <Label>Password</Label>
              <div className="relative">
                <Input type={showPwd ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" />
                <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" onClick={() => setShowPwd(!showPwd)}>
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Checkbox id="remember" checked={remember} onCheckedChange={(v) => setRemember(!!v)} />
                <label htmlFor="remember" className="text-sm text-muted-foreground">Remember me</label>
              </div>
              <button type="button" className="text-sm text-primary hover:underline">Forgot Password?</button>
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in..." : "Sign In"}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground text-center mt-6">Demo credentials: admin / admin123</p>
        </CardContent>
      </Card>
    </div>
  );
}
