import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { UserPlus, Shield, Users, RefreshCw } from "lucide-react";
import { createAdminUser, listAdminUsers } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

const roleOptions = [
  { value: "officer", label: "Officer" },
  { value: "senior_officer", label: "Senior Officer" },
];

export default function AdminPanelPage() {
  const { toast } = useToast();
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState("officer");

  const { data: users = [], isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["adminUsers"],
    queryFn: listAdminUsers,
    refetchInterval: 30000,
  });

  const counts = useMemo(() => ({
    total: users.length,
    officers: users.filter((user) => user.role === "officer").length,
    seniors: users.filter((user) => user.role === "senior_officer").length,
  }), [users]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!username || !password || !confirmPassword) {
      toast({ title: "Missing data", description: "Fill username and password fields.", variant: "destructive" });
      return;
    }
    if (password !== confirmPassword) {
      toast({ title: "Password mismatch", description: "Password and confirm password must match.", variant: "destructive" });
      return;
    }

    try {
      await createAdminUser({
        username,
        password,
        confirm_password: confirmPassword,
        role,
        full_name: fullName,
      });
      toast({ title: "User created", description: `${username} is now active with ${role} access.` });
      setUsername("");
      setFullName("");
      setPassword("");
      setConfirmPassword("");
      setRole("officer");
      refetch();
    } catch (error: any) {
      toast({ title: "Creation failed", description: error.message || "Unable to create user.", variant: "destructive" });
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black font-display text-foreground tracking-tight uppercase">Admin Panel</h1>
          <p className="text-[10px] text-muted-foreground mt-1 uppercase tracking-[0.2em] font-bold flex items-center gap-2 opacity-80">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-40"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary shadow-[0_0_8px_hsl(var(--primary))]"></span>
            </span>
            User provisioning and access control
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-primary" />}
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard title="Total Users" value={counts.total} icon={Users} />
        <StatCard title="Officers" value={counts.officers} icon={Shield} />
        <StatCard title="Senior Officers" value={counts.seniors} icon={Shield} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6">
        <Card className="shadow-card border-border">
          <CardHeader>
            <CardTitle className="font-display flex items-center gap-2"><UserPlus className="h-5 w-5 text-primary" /> Create User</CardTitle>
            <CardDescription>Provision officers and senior officers with a hashed password.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-2">
                <Label>Username</Label>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="new.user" />
              </div>
              <div className="space-y-2">
                <Label>Full Name</Label>
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Display name" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Password</Label>
                  <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Confirm Password</Label>
                  <Input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
                </div>
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <div className="grid grid-cols-2 gap-2">
                  {roleOptions.map((item) => (
                    <Button
                      key={item.value}
                      type="button"
                      variant={role === item.value ? "default" : "outline"}
                      onClick={() => setRole(item.value)}
                      className="justify-start"
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
              </div>
              <Button type="submit" className="w-full">Create User</Button>
            </form>
          </CardContent>
        </Card>

        <Card className="shadow-card border-border overflow-hidden">
          <CardHeader>
            <CardTitle className="font-display">System Users</CardTitle>
            <CardDescription>Login credentials are stored hashed in the database.</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-40 bg-muted rounded animate-pulse" />
            ) : isError ? (
              <div className="text-sm text-destructive">Failed to load users.</div>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Username</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Role</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell className="font-mono text-primary">{user.username}</TableCell>
                        <TableCell>{user.name || user.username}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{user.role}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon: Icon }: { title: string; value: number; icon: any }) {
  return (
    <Card className="shadow-card border-border">
      <CardContent className="p-5 flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-3xl font-bold text-foreground">{value}</p>
        </div>
        <Icon className="h-5 w-5 text-primary" />
      </CardContent>
    </Card>
  );
}