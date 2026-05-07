import { Navigate, Outlet, useLocation } from "react-router-dom";

export default function ProtectedRoute() {
  const location = useLocation();
  const authStr = localStorage.getItem("officer_auth");
  const auth = authStr ? JSON.parse(authStr) : null;
  const role = String(auth?.role || "").toLowerCase();
  const pathRole = location.pathname.startsWith("/admin")
    ? "admin"
    : location.pathname.startsWith("/senior-officer")
      ? "senior_officer"
      : "officer";
  
  console.log("[ProtectedRoute] Path:", location.pathname, "Auth:", auth);

  if (!auth || (!auth.email && !auth.username)) {
    console.log("[ProtectedRoute] Unauthorized access, redirecting to login");
    return <Navigate to="/officer/login" state={{ from: location }} replace />;
  }

  if (role && role !== pathRole) {
    const homePath = role === "admin"
      ? "/admin/dashboard"
      : role === "senior_officer"
        ? "/senior-officer/dashboard"
        : "/officer/dashboard";
    return <Navigate to={homePath} replace />;
  }

  return <Outlet />;
}
