import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import LandingPage from "./pages/LandingPage";
import ApplyPage from "./pages/ApplyPage";
import SuccessPage from "./pages/SuccessPage";
import TrackPage from "./pages/TrackPage";
import OfficerLoginPage from "./pages/officer/OfficerLoginPage";
import OfficerLayout from "./components/OfficerLayout";
import OfficerDashboardPage from "./pages/officer/OfficerDashboardPage";
import OfficerApplicationsPage from "./pages/officer/OfficerApplicationsPage";
import OfficerApplicationDetailPage from "./pages/officer/OfficerApplicationDetailPage";
import OfficerAnalyticsPage from "./pages/officer/OfficerAnalyticsPage";
import OfficerProfilePage from "./pages/officer/OfficerProfilePage";
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

          {/* Officer Portal */}
          <Route path="/officer/login" element={<OfficerLoginPage />} />
          <Route path="/officer" element={<OfficerLayout />}>
            <Route path="dashboard" element={<OfficerDashboardPage />} />
            <Route path="applications" element={<OfficerApplicationsPage />} />
            <Route path="applications/:id" element={<OfficerApplicationDetailPage />} />
            <Route path="analytics" element={<OfficerAnalyticsPage />} />
            <Route path="profile" element={<OfficerProfilePage />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
