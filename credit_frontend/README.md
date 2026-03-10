# Loan Credit Risk Assessment Dashboard

A modern, clean admin dashboard UI for a Loan Credit Risk Assessment System built with React, Vite, TailwindCSS, and Axios. This fintech internal tool allows bankers to upload loan application PDFs, track processing status, and view credit risk assessments.

## 🚀 Features

### ✨ Dashboard
- **Drag-and-drop PDF upload** with file validation
- **Real-time processing status** tracking with three stages:
  - Document Parsing
  - Credit Risk Analysis  
  - Fraud Check
- **Credit Score Card** display with:
  - Credit score (0-850 scale)
  - Risk category (Low/Medium/High)
  - Recommendation (Approve/Reject/Conditional)
  - Detailed analysis breakdown

### 📊 Application History
- **Searchable table** of all previous applications
- **Status filtering** (Completed/Processing/Failed)
- **Export functionality** for individual or bulk reports
- **Pagination** for large datasets

### 🎨 Design
- **Clean, minimal UI** designed for fintech professionals
- **Responsive layout** that works on desktop and tablets
- **Professional color scheme** with consistent branding
- **Intuitive navigation** with sidebar layout

## 🛠️ Technology Stack

- **React 18** - Frontend framework
- **Vite** - Build tool and development server
- **TailwindCSS** - Utility-first CSS framework
- **Axios** - HTTP client for API calls
- **React Router** - Client-side routing
- **React Dropzone** - File upload functionality
- **Lucide React** - Modern icon library

## 📁 Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── Sidebar.jsx     # Navigation sidebar
│   ├── FileUpload.jsx  # PDF upload component
│   ├── ProcessingStatus.jsx  # Status tracking component
│   └── CreditScoreCard.jsx   # Results display component
├── pages/              # Page components
│   ├── Dashboard.jsx   # Main dashboard page
│   └── ApplicationHistory.jsx  # History table page
├── services/           # API and external services
│   └── api.js          # Axios configuration and API methods
├── App.jsx             # Main app component with routing
├── main.jsx            # Application entry point
├── index.css           # Global styles with Tailwind imports
├── README.md           # Project documentation
└── BACKEND_INTEGRATION.md  # Complete backend API guide
```

## 🔌 API Integration

The frontend is designed to be API-ready with the following endpoints:

> **📋 For Backend Developers**: See [BACKEND_INTEGRATION.md](BACKEND_INTEGRATION.md) for complete API implementation guide

### POST `/api/applications/upload`
Upload a PDF loan application
```json
// Request: multipart/form-data with 'file' field
// Response:
{
  "application_id": "uuid",
  "status": "processing"
}
```

### GET `/api/applications/{id}/status`
Check processing status
```json
// Response:
{
  "document_parsing": "completed",
  "credit_analysis": "running", 
  "fraud_check": "waiting",
  "overall_status": "processing"
}
```

### GET `/api/applications/{id}/result`
Fetch analysis results
```json
// Response:
{
  "credit_score": 720,
  "risk_category": "low",
  "recommendation": "approve",
  "analysis_details": {
    "key_factors": ["Stable income", "Low debt ratio"],
    "risk_indicators": [],
    "positive_factors": ["Good payment history"],
    "notes": "Strong application with minimal risk factors"
  }
}
```

### GET `/api/applications/history`
Fetch application history
```json
// Response:
{
  "applications": [
    {
      "id": "uuid",
      "filename": "loan_app_john_doe.pdf",
      "submitted_at": "2024-03-08T14:30:00Z",
      "status": "completed",
      "credit_score": 720,
      "risk_category": "low",
      "recommendation": "approve"
    }
  ],
  "total_pages": 5,
  "current_page": 1
}
```

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ and npm/yarn
- Modern web browser

### Installation

1. **Clone and install dependencies:**
   ```bash
   cd loan-risk-dashboard
   npm install
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API base URL
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```

4. **Open your browser:**
   ```
   http://localhost:3000
   ```

### Backend Integration

- **For Backend Developers**: Complete API implementation guide in [BACKEND_INTEGRATION.md](BACKEND_INTEGRATION.md)
- **Frontend Developers**: The UI works standalone with mock data until backend is connected

### Build for Production

```bash
npm run build
npm run preview  # Preview production build locally
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_APP_NAME=LoanRisk Dashboard
VITE_APP_VERSION=1.0.0
```

### API Configuration

The API service ([src/services/api.js](src/services/api.js)) includes:
- Request/response interceptors
- Error handling
- Authentication token support  
- Configurable base URL and timeout

## 🎯 Usage

### Uploading Applications

1. Navigate to the Dashboard
2. Drag and drop a PDF file or click to select
3. Click "Analyze Application" 
4. Monitor real-time processing status
5. View results when analysis completes

### Viewing History

1. Click "Application History" in the sidebar
2. Search by filename or filter by status
3. Click actions to view details or export reports
4. Use pagination to navigate through results

## 🤝 Backend Integration

The frontend is designed to work seamlessly with any backend that implements the API contract. Mock data is shown when the API is unavailable, making it easy to develop and test the UI independently.

### Key Integration Points:

- **File Upload**: Handles multipart form data with progress tracking
- **Status Polling**: Automatically polls for status updates every 2 seconds
- **Error Handling**: Graceful fallback to mock data when API is unavailable
- **Authentication**: Ready for JWT token integration

## 📱 Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 🎨 Customization

### Colors and Branding
- Edit [tailwind.config.js](tailwind.config.js) to customize the color palette
- Update logo and branding in [src/components/Sidebar.jsx](src/components/Sidebar.jsx)

### Adding New Features
- Create new components in `src/components/`
- Add new pages in `src/pages/`
- Update routing in [src/App.jsx](src/App.jsx)
- Add new API endpoints in [src/services/api.js](src/services/api.js)

## 📄 License

This project is licensed under the MIT License.

---

Built with ❤️ for modern fintech applications