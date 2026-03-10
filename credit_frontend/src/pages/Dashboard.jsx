import React, { useState, useEffect } from 'react';
import { AlertCircle } from 'lucide-react';
import FileUpload from '../components/FileUpload';
import ProcessingStatus from '../components/ProcessingStatus';
import CreditScoreCard from '../components/CreditScoreCard';
import { apiService } from '../services/api';

const Dashboard = () => {
  const [currentApplication, setCurrentApplication] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isDemoMode, setIsDemoMode] = useState(false);

  // Poll for status updates when processing
  useEffect(() => {
    let intervalId;
    
    if (currentApplication && processing) {
      intervalId = setInterval(async () => {
        try {
          const status = await apiService.checkStatus(currentApplication.id);
          
          // Update current application with status
          setCurrentApplication(prev => ({
            ...prev,
            status: status
          }));

          // Check if processing is complete
          if (status.overall_status === 'completed') {
            setProcessing(false);
            // Fetch the final result
            const resultData = await apiService.getResult(currentApplication.id);
            setResult(resultData);
          } else if (status.overall_status === 'failed') {
            setProcessing(false);
            setError('Processing failed. Please try again.');
          }
        } catch (err) {
          console.error('Error checking status:', err);
          // Continue polling unless it's a critical error
        }
      }, 2000); // Poll every 2 seconds
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [currentApplication, processing]);

  const handleFileUpload = async (file) => {
    try {
      setError(null);
      setResult(null);
      setProcessing(true);

      // Upload the file
      const response = await apiService.uploadApplication(file);
      
      // Check if we got a demo response (mock mode)
      if (response.application_id.startsWith('app_')) {
        setIsDemoMode(true);
      }
      
      // Set the current application
      setCurrentApplication({
        id: response.application_id,
        filename: file.name,
        status: {
          document_parsing: 'waiting',
          credit_analysis: 'waiting',
          fraud_check: 'waiting',
          overall_status: 'processing'
        }
      });

    } catch (err) {
      let errorMessage = 'Failed to upload file. Please try again.';
      
      // Show more specific error messages
      if (err.message.includes('PDF file only')) {
        errorMessage = 'Please upload a PDF file only.';
      } else if (err.message.includes('10MB')) {
        errorMessage = 'File size must be less than 10MB.';
      }
      
      setError(errorMessage);
      setProcessing(false);
      console.error('Upload error:', err);
    }
  };

  const handleNewApplication = () => {
    setCurrentApplication(null);
    setProcessing(false);
    setResult(null);
    setError(null);
    setIsDemoMode(false);
  };

  return (
    <div className="flex-1 overflow-auto">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
            <p className="text-sm text-gray-600 mt-1">
              Upload and analyze loan applications
            </p>
          </div>
          
          {(processing || result) && (
            <button
              onClick={handleNewApplication}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors duration-200"
            >
              New Application
            </button>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="p-6">
        {isDemoMode && (
          <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center">
            <AlertCircle className="h-5 w-5 text-blue-500 mr-2" />
            <div>
              <span className="text-blue-700 font-medium">Demo Mode Active</span>
              <span className="text-blue-600 ml-2">
                No backend detected - using simulated processing for demonstration
              </span>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4 flex items-center">
            <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
            <span className="text-red-700">{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* File Upload Section */}
          <div className="lg:col-span-2">
            <FileUpload 
              onUpload={handleFileUpload} 
              disabled={processing}
              currentFile={currentApplication?.filename}
            />
          </div>

          {/* Processing Status */}
          {currentApplication && processing && (
            <div className="lg:col-span-2">
              <ProcessingStatus 
                status={currentApplication.status}
                filename={currentApplication.filename}
              />
            </div>
          )}

          {/* Results */}
          {result && !processing && (
            <div className="lg:col-span-2">
              <CreditScoreCard 
                score={result.credit_score}
                riskCategory={result.risk_category}
                recommendation={result.recommendation}
                details={result.analysis_details}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;