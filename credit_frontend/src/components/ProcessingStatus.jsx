import React from 'react';
import { Clock, Play, CheckCircle, XCircle, Loader2 } from 'lucide-react';

const ProcessingStatus = ({ status, filename }) => {
  const steps = [
    {
      key: 'document_parsing',
      title: 'Document Parsing',
      description: 'Extracting data from PDF document'
    },
    {
      key: 'credit_analysis',
      title: 'Credit Risk Analysis',
      description: 'AI agents analyzing creditworthiness'
    },
    {
      key: 'fraud_check',
      title: 'Fraud Check',
      description: 'Detecting potential fraud indicators'
    }
  ];

  const getStatusIcon = (stepStatus) => {
    switch (stepStatus) {
      case 'waiting':
        return <Clock className="h-5 w-5 text-gray-400" />;
      case 'running':
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Clock className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusColor = (stepStatus) => {
    switch (stepStatus) {
      case 'waiting':
        return 'text-gray-600';
      case 'running':
        return 'text-blue-600';
      case 'completed':
        return 'text-green-600';
      case 'failed':
        return 'text-red-600';
      default:
        return 'text-gray-600';
    }
  };

  const getProgressPercentage = () => {
    const completedSteps = steps.filter(step => status[step.key] === 'completed').length;
    return (completedSteps / steps.length) * 100;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">Processing Status</h3>
        <div className="text-sm text-gray-500">
          File: {filename}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Overall Progress</span>
          <span>{Math.round(getProgressPercentage())}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-primary-600 h-2 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${getProgressPercentage()}%` }}
          ></div>
        </div>
      </div>

      {/* Status Steps */}
      <div className="space-y-4">
        {steps.map((step, index) => {
          const stepStatus = status[step.key] || 'waiting';
          const isLast = index === steps.length - 1;

          return (
            <div key={step.key} className="relative">
              {/* Connector Line */}
              {!isLast && (
                <div className="absolute left-2.5 top-8 w-0.5 h-6 bg-gray-200"></div>
              )}
              
              <div className="flex items-start space-x-3">
                {/* Status Icon */}
                <div className="flex-shrink-0">
                  {getStatusIcon(stepStatus)}
                </div>
                
                {/* Step Content */}
                <div className="flex-grow min-w-0">
                  <div className="flex items-center justify-between">
                    <h4 className={`text-sm font-medium ${getStatusColor(stepStatus)}`}>
                      {step.title}
                    </h4>
                    <span className={`text-xs font-medium uppercase tracking-wide ${getStatusColor(stepStatus)}`}>
                      {stepStatus}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{step.description}</p>
                  
                  {/* Show additional info for running status */}
                  {stepStatus === 'running' && (
                    <div className="flex items-center mt-2 text-xs text-blue-600">
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      Processing...
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Overall Status */}
      <div className="mt-6 pt-4 border-t border-gray-200">
        <div className="text-center">
          {status.overall_status === 'processing' && (
            <div className="flex items-center justify-center text-sm text-blue-600">
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Analysis in progress...
            </div>
          )}
          {status.overall_status === 'completed' && (
            <div className="flex items-center justify-center text-sm text-green-600">
              <CheckCircle className="h-4 w-4 mr-2" />
              Analysis completed successfully
            </div>
          )}
          {status.overall_status === 'failed' && (
            <div className="flex items-center justify-center text-sm text-red-600">
              <XCircle className="h-4 w-4 mr-2" />
              Analysis failed
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProcessingStatus;