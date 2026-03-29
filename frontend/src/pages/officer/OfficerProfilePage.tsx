import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { User, Bell, Shield, Wallet, Save, RefreshCw } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Switch } from "@/components/ui/switch";

export default function OfficerProfilePage() {
  const auth = JSON.parse(localStorage.getItem("officer_auth") || '{"name":"Officer","email":"officer@aria.ai","role":"Senior Risk Officer","id":"OFF772"}');
  const [name, setName] = useState(auth.name);
  const [email, setEmail] = useState(auth.email);
  const { toast } = useToast();

  const save = () => {
    localStorage.setItem("officer_auth", JSON.stringify({ ...auth, name, email }));
    toast({ title: "Settings Saved", description: "Your profile and preferences have been updated." });
  };

  return (
    <div className="max-w-4xl space-y-6 animate-fade-in pb-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold font-display text-foreground">Officer Settings</h1>
        <Button onClick={save}><Save className="h-4 w-4 mr-2" /> Save Changes</Button>
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
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
