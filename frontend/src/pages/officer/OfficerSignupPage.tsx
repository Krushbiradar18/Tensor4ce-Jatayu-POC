import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ShieldCheck, MailCheck, ArrowLeft, Eye, EyeOff } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { publicSignup, resendSignupOtp, verifySignupOtp } from "@/lib/api";

export default function OfficerSignupPage() {
  const [step, setStep] = useState<"signup" | "verify">("signup");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
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

  const persistSession = (response: any) => {
    if (response?.user) {
      localStorage.setItem("officer_auth", JSON.stringify(response.user));
    }
    if (response?.token) {
      localStorage.setItem("officer_token", response.token);
    }
  };

  const handleSignup = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!username || !password || !confirmPassword) {
      toast({ title: "Missing data", description: "Fill the email and password fields.", variant: "destructive" });
      return;
    }
    if (password !== confirmPassword) {
      toast({ title: "Password mismatch", description: "Password and confirm password must match.", variant: "destructive" });
      return;
    }

    setLoading(true);
    try {
      const response = await publicSignup({
        username,
        password,
        confirm_password: confirmPassword,
        full_name: fullName,
      });
      if (response.verification_required) {
        setStep("verify");
        toast({ title: "Verification sent", description: response.message || "Check your email for the OTP." });
      }
    } catch (error: any) {
      toast({ title: "Signup failed", description: error.message || "Unable to create account.", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!otp || otp.length < 6) {
      toast({ title: "Missing OTP", description: "Enter the 6-digit code from your email.", variant: "destructive" });
      return;
    }

    setLoading(true);
    try {
      const response = await verifySignupOtp({ username, otp });
      persistSession(response);
      toast({ title: "Account verified", description: "Your account is ready to use." });
      navigate(getHomePath(response.user?.role));
    } catch (error: any) {
      toast({ title: "Verification failed", description: error.message || "Unable to verify OTP.", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    try {
      const response = await resendSignupOtp({ username });
      toast({ title: "OTP resent", description: response.message || "A new code has been emailed." });
    } catch (error: any) {
      toast({ title: "Resend failed", description: error.message || "Unable to resend code.", variant: "destructive" });
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')] pointer-events-none" />
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-accent/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2 pointer-events-none" />

      <Card className="w-full max-w-md shadow-elevated animate-fade-in border-border/50 relative z-10 bg-card">
        <CardHeader className="text-center pb-2 pt-8">
          <div className="relative group mx-auto mb-6">
            <div className="absolute -inset-1.5 bg-gradient-to-r from-primary to-accent rounded-2xl blur opacity-25 group-hover:opacity-40 transition duration-1000 group-hover:duration-200" />
            <div className="relative w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center border border-primary/20 shadow-sm transition-transform duration-500 group-hover:scale-105">
              {step === "signup" ? <ShieldCheck className="h-11 w-11 text-primary animate-pulse" /> : <MailCheck className="h-11 w-11 text-primary animate-pulse" />}
            </div>
          </div>
          <CardTitle className="text-3xl font-black font-display tracking-tight text-foreground uppercase">
            ARIA <span className="text-primary italic">AI</span>
          </CardTitle>
          <div className="flex flex-col items-center gap-1 mt-1">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em] leading-none">
              {step === "signup" ? "Create Account" : "Verify Email"}
            </span>
            <CardDescription className="text-muted-foreground mt-2 text-sm font-medium">
              {step === "signup"
                ? "Create your officer account, then confirm the OTP sent to your email."
                : `Enter the 6-digit code sent to ${username}.`}
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {step === "signup" ? (
            <form onSubmit={handleSignup} className="space-y-6 pt-4">
              <div className="space-y-2">
                <Label className="text-foreground/80 font-medium">Email Address</Label>
                <Input
                  type="email"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="name@company.com"
                  className="h-11 border-border focus-visible:ring-primary/20"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-foreground/80 font-medium">Full Name</Label>
                <Input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Your name"
                  className="h-11 border-border focus-visible:ring-primary/20"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-foreground/80 font-medium">Password</Label>
                <div className="relative">
                  <Input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="h-11 border-border focus-visible:ring-primary/20"
                  />
                  <button 
                    type="button" 
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary transition-colors focus:outline-none" 
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-foreground/80 font-medium">Confirm Password</Label>
                <div className="relative">
                  <Input
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className="h-11 border-border focus-visible:ring-primary/20"
                  />
                  <button 
                    type="button" 
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary transition-colors focus:outline-none" 
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <Button type="submit" className="w-full h-12 bg-primary text-primary-foreground font-bold text-base hover:opacity-90 shadow-md transition-all" disabled={loading}>
                {loading ? "Creating Account..." : "Create Account"}
              </Button>
              <div className="flex items-center justify-center pt-2">
                <Link to="/officer/login" className="text-sm text-primary hover:underline font-semibold">
                  Already have an account?
                </Link>
              </div>
            </form>
          ) : (
            <form onSubmit={handleVerify} className="space-y-6 pt-4">
              <div className="space-y-3">
                <Label className="text-foreground/80 font-medium">Verification Code</Label>
                <InputOTP maxLength={6} value={otp} onChange={setOtp}>
                  <InputOTPGroup>
                    <InputOTPSlot index={0} />
                    <InputOTPSlot index={1} />
                    <InputOTPSlot index={2} />
                    <InputOTPSlot index={3} />
                    <InputOTPSlot index={4} />
                    <InputOTPSlot index={5} />
                  </InputOTPGroup>
                </InputOTP>
              </div>
              <Button type="submit" className="w-full h-12 bg-primary text-primary-foreground font-bold text-base hover:opacity-90 shadow-md transition-all" disabled={loading}>
                {loading ? "Verifying..." : "Verify and Continue"}
              </Button>
              <div className="flex items-center justify-between gap-3">
                <Button type="button" variant="outline" className="flex-1" onClick={() => setStep("signup")}>
                  <ArrowLeft className="h-4 w-4 mr-2" /> Back
                </Button>
                <Button type="button" variant="secondary" className="flex-1" onClick={handleResend} disabled={resending}>
                  {resending ? "Resending..." : "Resend OTP"}
                </Button>
              </div>
            </form>
          )}
          <div className="mt-8 pt-6 border-t border-border/50">
            <p className="text-[10px] text-muted-foreground text-center uppercase tracking-widest leading-loose font-medium opacity-60">
              Authorized personnel only. <br />All access attempts are monitored.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
