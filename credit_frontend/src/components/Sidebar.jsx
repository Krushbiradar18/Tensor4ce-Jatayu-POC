import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FileText, Shield } from 'lucide-react';

const Sidebar = () => {
  const location = useLocation();

  const isActive = location.pathname === '/applications' || location.pathname === '/';

  return (
    <div className="w-64 bg-white shadow-lg flex flex-col">
      {/* Logo / Header */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center space-x-2">
          <Shield className="h-8 w-8 text-primary-600" />
          <div>
            <h1 className="text-lg font-semibold text-gray-900">LoanRisk</h1>
            <p className="text-sm text-gray-500">Admin Dashboard</p>
          </div>
        </div>
      </div>

      {/* Navigation Menu */}
      <nav className="mt-6 flex-1">
        <Link
          to="/applications"
          className={`flex items-center px-6 py-3 text-sm font-medium transition-colors duration-200 ${
            isActive
              ? 'text-primary-600 bg-primary-50 border-r-2 border-primary-600'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
          }`}
        >
          <FileText className="mr-3 h-5 w-5" />
          Applications
        </Link>
      </nav>

      {/* Footer */}
      <div className="p-6 border-t border-gray-200">
        <div className="text-xs text-gray-500">
          <p>Version 1.0.0</p>
          <p>© 2024 LoanRisk Systems</p>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;