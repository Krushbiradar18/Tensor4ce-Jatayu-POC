import { Navigate, Outlet, useLocation } from "react-router-dom";

export default function ProtectedRoute() {
  const location = useLocation();
  const authStr = localStorage.getItem("officer_auth");
  const auth = authStr ? JSON.parse(authStr) : null;
  
  console.log("[ProtectedRoute] Path:", location.pathname, "Auth:", auth);

  if (!auth || !auth.email) {
    console.log("[ProtectedRoute] Unauthorized access, redirecting to login");
    return <Navigate to="/officer/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
