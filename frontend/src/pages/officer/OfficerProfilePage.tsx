import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { User, Shield, Wallet, Save, Mail, Smartphone } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Switch } from "@/components/ui/switch";
import { setupTotpAuthenticator, updateTwoFactorSettings, verifyTotpAuthenticator } from "@/lib/api";
import QRCode from "qrcode";

export default function OfficerProfilePage() {
  const auth = JSON.parse(localStorage.getItem("officer_auth") || '{"name":"Officer","email":"officer@aria.ai","role":"Senior Risk Officer","id":"OFF772"}');
  const [name, setName] = useState(auth.name);
  const [email, setEmail] = useState(auth.email);
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(!!auth.two_factor_enabled);
  const [twoFactorMethod, setTwoFactorMethod] = useState<"email" | "authenticator">((auth.two_factor_method as "email" | "authenticator") || "email");
  const [saving2fa, setSaving2fa] = useState(false);
  const [totpSetup, setTotpSetup] = useState<{ secret: string; otpauthUri: string } | null>(null);
  const [totpQr, setTotpQr] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [totpSetupLoading, setTotpSetupLoading] = useState(false);
  const [totpVerifyLoading, setTotpVerifyLoading] = useState(false);
  const [totpVerified, setTotpVerified] = useState(!!auth.two_factor_enabled && auth.two_factor_method === "authenticator");
  const [showTotpSetup, setShowTotpSetup] = useState(false);
  const { toast } = useToast();

  const saveProfile = () => {
    localStorage.setItem("officer_auth", JSON.stringify({ ...auth, name, email }));
    toast({ title: "Settings Saved", description: "Your profile and preferences have been updated." });
  };

  const saveTwoFactor = async () => {
    if (twoFactorEnabled && twoFactorMethod === "authenticator" && !totpVerified) {
      toast({
        title: "Complete setup",
        description: "Verify the 6-digit authenticator code before enabling this method.",
        variant: "destructive",
      });
      return;
    }

    setSaving2fa(true);
    try {
      const response = await updateTwoFactorSettings({
        enabled: twoFactorEnabled,
        method: twoFactorMethod,
      });
      localStorage.setItem(
        "officer_auth",
        JSON.stringify({
          ...auth,
          ...response.user,
          name,
          email,
          two_factor_enabled: twoFactorEnabled,
          two_factor_method: twoFactorMethod,
        })
      );
      toast({
        title: "Two-factor updated",
        description: twoFactorEnabled
          ? twoFactorMethod === "authenticator"
            ? "Login verification will now require a TOTP code from your authenticator app."
            : "Login verification will now require an OTP by email."
          : "Login verification has been disabled.",
      });
    } catch (error: any) {
      toast({ title: "Update failed", description: error.message || "Unable to update 2FA settings.", variant: "destructive" });
    } finally {
      setSaving2fa(false);
    }
  };

  const handleTotpSetup = async () => {
    setTotpSetupLoading(true);
    try {
      const response = await setupTotpAuthenticator();
      setTotpSetup({ secret: response.secret, otpauthUri: response.otpauth_uri });
      const qrDataUrl = await QRCode.toDataURL(response.otpauth_uri, { margin: 1, width: 220 });
      setTotpQr(qrDataUrl);
      setTotpCode("");
      toast({ title: "Authenticator ready", description: "Scan the QR code and enter the 6-digit code." });
    } catch (error: any) {
      toast({ title: "Setup failed", description: error.message || "Unable to start authenticator setup.", variant: "destructive" });
    } finally {
      setTotpSetupLoading(false);
    }
  };

  const handleTotpVerify = async () => {
    if (!totpCode || totpCode.length < 6) {
      toast({ title: "Missing code", description: "Enter the 6-digit code from your authenticator app.", variant: "destructive" });
      return;
    }

    setTotpVerifyLoading(true);
    try {
      const response = await verifyTotpAuthenticator({ otp: totpCode });
      setTotpVerified(true);
      setTwoFactorEnabled(true);
      setTwoFactorMethod("authenticator");
      setShowTotpSetup(false);
      localStorage.setItem(
        "officer_auth",
        JSON.stringify({
          ...auth,
          ...response.user,
          name,
          email,
          two_factor_enabled: true,
          two_factor_method: "authenticator",
        })
      );
      toast({ title: "Authenticator enabled", description: "Your account now requires a TOTP code on login." });
    } catch (error: any) {
      toast({ title: "Verification failed", description: error.message || "Unable to verify authenticator code.", variant: "destructive" });
    } finally {
      setTotpVerifyLoading(false);
    }
  };

  const handleCopySecret = async () => {
    if (!totpSetup?.secret) return;
    try {
      await navigator.clipboard.writeText(totpSetup.secret);
      toast({ title: "Secret copied", description: "Authenticator secret copied to clipboard." });
    } catch (error: any) {
      toast({ title: "Copy failed", description: "Unable to copy the secret right now.", variant: "destructive" });
    }
  };

  return (
    <div className="max-w-4xl space-y-6 animate-fade-in pb-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold font-display text-foreground">Officer Settings</h1>
        <Button onClick={saveProfile}><Save className="h-4 w-4 mr-2" /> Save Profile</Button>
      </div>

      <Tabs defaultValue="profile" className="w-full">
        <TabsList className="bg-muted lg:w-[200px]">
          <TabsTrigger value="profile" className="flex items-center gap-2 w-full"><User className="h-4 w-4" /> Profile</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-6">
          <Card className="shadow-card">
            <CardHeader>
              <div className="flex items-center gap-4">
                <div className="w-20 h-20 rounded-full bg-primary flex items-center justify-center border-4 border-background shadow-elevated">
                  <User className="h-10 w-10 text-primary-foreground" />
                </div>
                <div>
                  <CardTitle className="font-display text-xl">{name}</CardTitle>
                  <CardDescription>Officer ID: <span className="font-mono text-primary">{auth.id}</span> • {auth.role}</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label>Full Name</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Professional Email</Label>
                  <Input value={email} onChange={(e) => setEmail(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Role</Label>
                  <Input value={auth.role} disabled className="bg-muted opacity-80" />
                </div>
                <div className="space-y-2">
                  <Label>Department</Label>
                  <Input value="Retail Assets" disabled className="bg-muted opacity-80" />
                </div>
              </div>
              <div className="p-4 bg-muted/30 border border-border rounded-lg">
                <h4 className="text-sm font-semibold mb-2 flex items-center gap-2"><Wallet className="h-4 w-4 text-primary" /> Authority Limits</h4>
                <p className="text-xs text-muted-foreground">Up to ₹50,00,000 for Personal Loans. Up to ₹2,00,00,000 for Home Loans. Higher amounts require escalation.</p>
              </div>

              <div className="p-4 bg-muted/30 border border-border rounded-lg space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h4 className="text-sm font-semibold flex items-center gap-2"><Shield className="h-4 w-4 text-primary" /> Login Two-Factor Authentication</h4>
                    <p className="text-xs text-muted-foreground mt-1">Add a second step after password entry for officer login.</p>
                  </div>
                  <Switch checked={twoFactorEnabled} onCheckedChange={setTwoFactorEnabled} />
                </div>

                <div className={`grid gap-3 ${twoFactorEnabled ? "opacity-100" : "opacity-60"}`}>
                  <div className="flex items-center justify-between rounded-md border border-border bg-background/60 px-3 py-2">
                    <div className="flex items-center gap-3">
                      <Mail className="h-4 w-4 text-primary" />
                      <div>
                        <p className="text-sm font-medium">Email OTP</p>
                        <p className="text-xs text-muted-foreground">Verification code sent to your email.</p>
                      </div>
                    </div>
                    <Button type="button" variant={twoFactorMethod === "email" ? "default" : "outline"} size="sm" onClick={() => setTwoFactorMethod("email")}>
                      {twoFactorMethod === "email" ? "Selected" : "Use"}
                    </Button>
                  </div>

                  <div className="flex items-center justify-between rounded-md border border-border bg-background/60 px-3 py-2">
                    <div className="flex items-center gap-3">
                      <Smartphone className={`h-4 w-4 ${twoFactorMethod === "authenticator" ? "text-primary" : "text-muted-foreground"}`} />
                      <div>
                        <p className="text-sm font-medium">Authenticator App</p>
                        <p className="text-xs text-muted-foreground">Use Google Authenticator, 1Password, or Authy.</p>
                      </div>
                    </div>
                    <Button type="button" variant={twoFactorMethod === "authenticator" ? "default" : "outline"} size="sm" onClick={() => setTwoFactorMethod("authenticator")}>
                      {twoFactorMethod === "authenticator" ? "Selected" : "Use"}
                    </Button>
                  </div>
                </div>

                {twoFactorMethod === "authenticator" && (totpVerified && !showTotpSetup ? (
                  <div className="rounded-md border border-border bg-background/60 p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center border border-emerald-200">
                        <Smartphone className="h-5 w-5 text-emerald-600" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold">Authenticator Active</p>
                        <p className="text-xs text-muted-foreground">Your device is linked and ready.</p>
                      </div>
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={() => setShowTotpSetup(true)}>
                      Reconfigure
                    </Button>
                  </div>
                ) : (
                  <div className="rounded-md border border-border bg-background/60 p-4 space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold">Authenticator setup</p>
                        <p className="text-xs text-muted-foreground">Scan the QR code or enter the secret manually.</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {totpVerified && (
                          <Button type="button" size="sm" variant="ghost" onClick={() => setShowTotpSetup(false)}>
                            Cancel
                          </Button>
                        )}
                        <Button type="button" size="sm" variant="secondary" onClick={handleTotpSetup} disabled={totpSetupLoading}>
                          {totpSetupLoading ? "Generating..." : totpSetup ? "Regenerate" : "Generate"}
                        </Button>
                      </div>
                    </div>

                    <div className="flex flex-col md:flex-row gap-4">
                      <div className="w-full md:w-48 h-48 rounded-md border border-border bg-muted/30 flex items-center justify-center">
                        {totpQr ? (
                          <img src={totpQr} alt="Authenticator QR code" className="w-40 h-40" />
                        ) : (
                          <span className="text-xs text-muted-foreground text-center px-4">Generate a QR code to continue.</span>
                        )}
                      </div>
                      <div className="flex-1 space-y-3">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs uppercase tracking-wide text-muted-foreground">Secret Key</Label>
                          <Button type="button" variant="ghost" size="sm" onClick={handleCopySecret} disabled={!totpSetup?.secret}>
                            Copy
                          </Button>
                        </div>
                        <Input value={totpSetup?.secret || ""} readOnly placeholder="Generate to reveal secret" className="font-mono" />
                        <div className="space-y-2">
                          <Label className="text-foreground/80 font-medium">6-digit code</Label>
                          <div className="flex items-center gap-3">
                            <Input value={totpCode} onChange={(e) => setTotpCode(e.target.value)} placeholder="123456" className="h-10 w-32 text-center font-mono" />
                            <Button type="button" onClick={handleTotpVerify} disabled={totpVerifyLoading || !totpSetup?.secret}>
                              {totpVerifyLoading ? "Verifying..." : totpVerified ? "Verified" : "Verify"}
                            </Button>
                          </div>
                        </div>
                        {totpVerified ? (
                          <p className="text-xs text-emerald-600">Authenticator is verified and ready for login.</p>
                        ) : (
                          <p className="text-xs text-muted-foreground">Verification enables TOTP for future logins.</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                <div className="flex justify-end">
                  <Button type="button" onClick={saveTwoFactor} disabled={saving2fa}>
                    {saving2fa ? "Updating..." : "Save 2FA Settings"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
