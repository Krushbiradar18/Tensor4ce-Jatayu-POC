import React from 'react';
import { Shield, TrendingUp, TrendingDown, AlertTriangle, CheckCircle } from 'lucide-react';

const CreditScoreCard = ({ score, riskCategory, recommendation, details }) => {
  const getScoreColor = (score) => {
    if (score >= 750) return 'text-green-600';
    if (score >= 650) return 'text-yellow-600';
    if (score >= 550) return 'text-orange-600';
    return 'text-red-600';
  };

  const getScoreBackground = (score) => {
    if (score >= 750) return 'bg-green-50 border-green-200';
    if (score >= 650) return 'bg-yellow-50 border-yellow-200';
    if (score >= 550) return 'bg-orange-50 border-orange-200';
    return 'bg-red-50 border-red-200';
  };

  const getRiskIcon = (category) => {
    switch (category.toLowerCase()) {
      case 'low':
        return <CheckCircle className="h-6 w-6 text-green-500" />;
      case 'medium':
        return <AlertTriangle className="h-6 w-6 text-yellow-500" />;
      case 'high':
        return <TrendingDown className="h-6 w-6 text-red-500" />;
      default:
        return <Shield className="h-6 w-6 text-gray-500" />;
    }
  };

  const getRiskColor = (category) => {
    switch (category.toLowerCase()) {
      case 'low':
        return 'text-green-600 bg-green-50 border-green-200';
      case 'medium':
        return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case 'high':
        return 'text-red-600 bg-red-50 border-red-200';
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getRecommendationIcon = (recommendation) => {
    if (recommendation.toLowerCase().includes('approve')) {
      return <CheckCircle className="h-5 w-5 text-green-500" />;
    } else if (recommendation.toLowerCase().includes('reject')) {
      return <AlertTriangle className="h-5 w-5 text-red-500" />;
    } else {
      return <TrendingUp className="h-5 w-5 text-yellow-500" />;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-primary-600 to-primary-700 px-6 py-4">
        <div className="flex items-center space-x-2">
          <Shield className="h-6 w-6 text-white" />
          <h3 className="text-lg font-semibold text-white">Credit Risk Assessment</h3>
        </div>
      </div>

      <div className="p-6">
        {/* Credit Score Section */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          {/* Credit Score */}
          <div className={`rounded-lg border-2 p-4 text-center ${getScoreBackground(score)}`}>
            <div className="flex items-center justify-center mb-2">
              <TrendingUp className={`h-8 w-8 ${getScoreColor(score)}`} />
            </div>
            <h4 className="text-sm font-medium text-gray-700 mb-1">Credit Score</h4>
            <div className={`text-3xl font-bold ${getScoreColor(score)}`}>
              {score}
            </div>
            <div className="text-xs text-gray-500 mt-1">out of 850</div>
          </div>

          {/* Risk Category */}
          <div className={`rounded-lg border-2 p-4 text-center ${getRiskColor(riskCategory)}`}>
            <div className="flex items-center justify-center mb-2">
              {getRiskIcon(riskCategory)}
            </div>
            <h4 className="text-sm font-medium text-gray-700 mb-1">Risk Category</h4>
            <div className="text-xl font-bold capitalize">
              {riskCategory} Risk
            </div>
          </div>

          {/* Recommendation */}
          <div className="rounded-lg border-2 border-gray-200 bg-gray-50 p-4 text-center">
            <div className="flex items-center justify-center mb-2">
              {getRecommendationIcon(recommendation)}
            </div>
            <h4 className="text-sm font-medium text-gray-700 mb-1">Recommendation</h4>
            <div className="text-lg font-semibold text-gray-900 capitalize">
              {recommendation}
            </div>
          </div>
        </div>

        {/* Analysis Details */}
        {details && (
          <div className="border-t border-gray-200 pt-6">
            <h4 className="text-sm font-semibold text-gray-900 mb-4">Analysis Details</h4>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Key Factors */}
              {details.key_factors && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <h5 className="text-sm font-medium text-gray-800 mb-2">Key Factors</h5>
                  <ul className="space-y-1">
                    {details.key_factors.map((factor, index) => (
                      <li key={index} className="text-sm text-gray-600 flex items-start">
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full mt-2 mr-2 flex-shrink-0"></span>
                        {factor}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Risk Indicators */}
              {details.risk_indicators && (
                <div className="bg-red-50 rounded-lg p-4">
                  <h5 className="text-sm font-medium text-red-800 mb-2">Risk Indicators</h5>
                  <ul className="space-y-1">
                    {details.risk_indicators.map((indicator, index) => (
                      <li key={index} className="text-sm text-red-700 flex items-start">
                        <AlertTriangle className="h-3 w-3 mt-0.5 mr-2 flex-shrink-0" />
                        {indicator}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Positive Factors */}
              {details.positive_factors && (
                <div className="bg-green-50 rounded-lg p-4">
                  <h5 className="text-sm font-medium text-green-800 mb-2">Positive Factors</h5>
                  <ul className="space-y-1">
                    {details.positive_factors.map((factor, index) => (
                      <li key={index} className="text-sm text-green-700 flex items-start">
                        <CheckCircle className="h-3 w-3 mt-0.5 mr-2 flex-shrink-0" />
                        {factor}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Additional Notes */}
              {details.notes && (
                <div className="bg-blue-50 rounded-lg p-4">
                  <h5 className="text-sm font-medium text-blue-800 mb-2">Additional Notes</h5>
                  <p className="text-sm text-blue-700">{details.notes}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="border-t border-gray-200 pt-6 mt-6">
          <div className="flex justify-end space-x-3">
            <button className="px-4 py-2 border border-gray-300 text-gray-700 bg-white rounded-lg hover:bg-gray-50 transition-colors duration-200">
              Export Report
            </button>
            <button className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors duration-200">
              Save to History
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreditScoreCard;