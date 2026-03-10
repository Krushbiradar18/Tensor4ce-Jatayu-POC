import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ApplicationHistory from './pages/ApplicationHistory';
import ReportPage from './pages/ReportPage';

function App() {
  return (
    <Routes>
      {/* Full-page report — no sidebar */}
      <Route path="/report" element={<ReportPage />} />

      {/* Main layout with sidebar */}
      <Route
        path="*"
        element={
          <div className="flex h-screen bg-gray-100">
            <Sidebar />
            <div className="flex-1 flex flex-col min-h-0">
              <main className="flex-1 overflow-y-auto">
                <Routes>
                  <Route path="/" element={<Navigate to="/applications" replace />} />
                  <Route path="/applications" element={<ApplicationHistory />} />
                  <Route path="*" element={<Navigate to="/applications" replace />} />
                </Routes>
              </main>
            </div>
          </div>
        }
      />
    </Routes>
  );
}

export default App;