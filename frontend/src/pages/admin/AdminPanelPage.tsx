import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { UserPlus, Shield, ShieldCheck, Users, RefreshCw } from "lucide-react";
import { createAdminUser, listAdminUsers, updateUserStatus, updateUserRoleByUsername, deleteUser } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

const roleOptions: { value: "officer" | "senior_officer"; label: string }[] = [
  { value: "officer", label: "Officer" },
  { value: "senior_officer", label: "Senior Officer" },
];

export default function AdminPanelPage() {
  const { toast } = useToast();
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<"officer" | "senior_officer">("officer");

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
      const result = await createAdminUser({
        username,
        password,
        confirm_password: confirmPassword,
        role,
        full_name: fullName,
      });
      toast({
        title: "User created",
        description: result.message || `${username} was created successfully.`,
      });
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

  const handleStatusToggle = async (user: any) => {
    try {
      await updateUserStatus(user.username, !user.is_active);
      toast({ title: "Status updated", description: `${user.username} is now ${!user.is_active ? "active" : "deactivated"}.` });
      refetch();
    } catch (error: any) {
      toast({ title: "Update failed", description: error.message, variant: "destructive" });
    }
  };

  const handleRoleChange = async (user: any, nextRole?: string) => {
    const roleToSet = nextRole || (user.role === "officer" ? "senior_officer" : "officer");
    try {
      await updateUserRoleByUsername(user.username, roleToSet);
      toast({ title: "Role updated", description: `${user.username} is now a ${roleToSet.replace('_', ' ')}.` });
      refetch();
    } catch (error: any) {
      toast({ title: "Update failed", description: error.message, variant: "destructive" });
    }
  };

  const handleDelete = async (user: any) => {
    if (!confirm(`Are you sure you want to delete ${user.username}?`)) return;
    try {
      await deleteUser(user.username);
      toast({ title: "User deleted", description: `${user.username} has been removed.` });
      refetch();
    } catch (error: any) {
      toast({ title: "Deletion failed", description: error.message, variant: "destructive" });
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

      <div className="pt-4">
        <div className="h-px bg-border w-full mb-8"></div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <Card className="shadow-card border-border">
          <CardHeader>
            <CardTitle className="font-display flex items-center gap-2"><UserPlus className="h-5 w-5 text-primary" /> Create User</CardTitle>
            <CardDescription>Provision officers and senior officers with a hashed password.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Username</Label>
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="new.user" />
                </div>
                <div className="space-y-2">
                  <Label>Full Name</Label>
                  <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Display name" />
                </div>
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
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {roleOptions.map((item) => {
                    const isSelected = role === item.value;
                    return (
                      <div
                        key={item.value}
                        onClick={() => setRole(item.value)}
                        className={`cursor-pointer p-4 rounded-xl border-2 transition-all duration-200 flex items-center gap-4 ${
                          isSelected 
                            ? "border-primary bg-primary/5 ring-1 ring-primary/20" 
                            : "border-border bg-card hover:border-primary/40 hover:bg-muted/30"
                        }`}
                      >
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          isSelected ? "bg-primary text-primary-foreground shadow-sm" : "bg-muted text-muted-foreground"
                        }`}>
                          {item.value === 'officer' ? <Shield className="h-5 w-5" /> : <ShieldCheck className="h-5 w-5" />}
                        </div>
                        <div className="flex-1 text-left">
                          <p className={`font-bold text-sm leading-none mb-1 ${isSelected ? "text-primary" : "text-foreground"}`}>
                            {item.label}
                          </p>
                          <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider opacity-70">
                            {item.value === 'officer' ? "Standard access" : "Advanced permissions"}
                          </p>
                        </div>
                        {isSelected && (
                          <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center animate-in zoom-in duration-300">
                            <div className="w-1.5 h-1.5 rounded-full bg-primary-foreground" />
                          </div>
                        )}
                      </div>
                    );
                  })}
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
                    <TableRow className="bg-muted/50">
                      <TableHead className="h-9 text-[11px] uppercase tracking-wider font-bold">Username</TableHead>
                      <TableHead className="h-9 text-[11px] uppercase tracking-wider font-bold">Name</TableHead>
                      <TableHead className="h-9 text-[11px] uppercase tracking-wider font-bold">Role</TableHead>
                      <TableHead className="h-9 text-[11px] uppercase tracking-wider font-bold">Status</TableHead>
                      <TableHead className="h-9 text-[11px] uppercase tracking-wider font-bold text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((user) => (
                      <TableRow key={user.id} className={`${!user.is_active ? "opacity-50" : ""} border-b transition-colors hover:bg-muted/30`}>
                        <TableCell className="font-mono text-primary text-xs py-2">
                          {user.username}
                          {user.needs_password_reset && (
                            <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-100 text-amber-800 uppercase tracking-tighter">
                              Reset Req.
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs py-2">{user.name || user.username}</TableCell>
                        <TableCell className="py-2">
                          <Badge variant="outline" className="capitalize text-[10px] px-1.5 py-0">{user.role.replace('_', ' ')}</Badge>
                        </TableCell>
                        <TableCell className="py-2">
                          <Badge variant={user.is_active ? "default" : "secondary"} className="text-[10px] px-1.5 py-0">
                            {user.is_active ? "Active" : "Revoked"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right py-2">
                          <div className="flex justify-end gap-1.5">
                            {user.username.toLowerCase() !== "admin" ? (
                              <>
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button 
                                      variant="outline" 
                                      size="xs" 
                                      className="gap-1 h-7 text-[10px] px-2"
                                    >
                                      <Shield className="h-3 w-3" />
                                      Role
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuLabel>Select New Role</DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem 
                                      onClick={() => handleRoleChange(user, "officer")}
                                      disabled={user.role === "officer"}
                                    >
                                      Officer
                                    </DropdownMenuItem>
                                    <DropdownMenuItem 
                                      onClick={() => handleRoleChange(user, "senior_officer")}
                                      disabled={user.role === "senior_officer"}
                                    >
                                      Senior Officer
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                                <Button 
                                  variant={user.is_active ? "outline" : "default"} 
                                  size="xs" 
                                  onClick={() => handleStatusToggle(user)}
                                  className="h-7 text-[10px] px-2"
                                >
                                  {user.is_active ? "Revoke" : "Activate"}
                                </Button>
                                <Button 
                                  variant="destructive" 
                                  size="xs" 
                                  onClick={() => handleDelete(user)}
                                  className="h-7 text-[10px] px-2"
                                >
                                  Delete
                                </Button>
                              </>
                            ) : (
                              <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest opacity-50 px-2">
                                System Protected
                              </span>
                            )}
                          </div>
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