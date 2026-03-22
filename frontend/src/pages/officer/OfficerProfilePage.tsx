import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { User } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function OfficerProfilePage() {
  const auth = JSON.parse(localStorage.getItem("officer_auth") || '{"name":"Officer","email":"officer@bankease.in","role":"Loan Officer"}');
  const [name, setName] = useState(auth.name);
  const [email, setEmail] = useState(auth.email);
  const { toast } = useToast();

  const save = () => {
    localStorage.setItem("officer_auth", JSON.stringify({ ...auth, name, email }));
    toast({ title: "Profile Updated", description: "Your changes have been saved." });
  };

  return (
    <div className="max-w-xl animate-fade-in space-y-6">
      <h1 className="text-2xl font-bold font-display text-foreground">Profile & Settings</h1>
      <Card className="shadow-card">
        <CardHeader>
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-primary flex items-center justify-center">
              <User className="h-8 w-8 text-primary-foreground" />
            </div>
            <div>
              <CardTitle className="font-display">{name}</CardTitle>
              <p className="text-sm text-muted-foreground">{auth.role}</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div><Label>Full Name</Label><Input value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><Label>Email</Label><Input value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><Label>Role</Label><Input value={auth.role} disabled className="opacity-60" /></div>
          <Button onClick={save}>Save Changes</Button>
        </CardContent>
      </Card>
    </div>
  );
}
