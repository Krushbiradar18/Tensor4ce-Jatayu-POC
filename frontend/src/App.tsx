import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import LandingPage from "./pages/LandingPage";
import ApplyPage from "./pages/ApplyPage";
import SuccessPage from "./pages/SuccessPage";
import TrackPage from "./pages/TrackPage";
import OfficerLoginPage from "./pages/officer/OfficerLoginPage";
import AboutPage from "./pages/AboutPage";
import ContactPage from "./pages/ContactPage";
import ProtectedRoute from "./components/ProtectedRoute";
import OfficerLayout from "./components/OfficerLayout";
import OfficerDashboardPage from "./pages/officer/OfficerDashboardPage";
import OfficerApplicationsPage from "./pages/officer/OfficerApplicationsPage";
import OfficerApplicationDetailPage from "./pages/officer/OfficerApplicationDetailPage";
import OfficerAnalyticsPage from "./pages/officer/OfficerAnalyticsPage";
import SeniorOfficerAnalyticsPage from "./pages/senior-officer/SeniorOfficerAnalyticsPage";
import OfficerProfilePage from "./pages/officer/OfficerProfilePage";
import AdminPanelPage from "./pages/admin/AdminPanelPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* Public Portal */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/apply" element={<ApplyPage />} />
          <Route path="/apply/success" element={<SuccessPage />} />
          <Route path="/track" element={<TrackPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/contact" element={<ContactPage />} />

          {/* Officer Portal */}
          <Route path="/officer/login" element={<OfficerLoginPage />} />
          <Route path="/officer" element={<ProtectedRoute />}>
            <Route element={<OfficerLayout />}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<OfficerDashboardPage />} />
              <Route path="applications" element={<OfficerApplicationsPage />} />
              <Route path="applications/:id" element={<OfficerApplicationDetailPage />} />
              <Route path="analytics" element={<OfficerAnalyticsPage />} />
              <Route path="profile" element={<OfficerProfilePage />} />
            </Route>
          </Route>

          {/* Admin Portal */}
          <Route path="/admin" element={<ProtectedRoute />}>
            <Route element={<OfficerLayout />}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<OfficerDashboardPage />} />
              <Route path="analytics" element={<OfficerAnalyticsPage />} />
              <Route path="admin-panel" element={<AdminPanelPage />} />
            </Route>
          </Route>

          {/* Senior Officer Portal */}
          <Route path="/senior-officer" element={<ProtectedRoute />}>
            <Route element={<OfficerLayout />}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<OfficerDashboardPage />} />
              <Route path="applications" element={<OfficerApplicationsPage />} />
              <Route path="applications/:id" element={<OfficerApplicationDetailPage />} />
              <Route path="analytics" element={<SeniorOfficerAnalyticsPage />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
