# Backend Integration Guide

This guide provides complete documentation for backend developers to implement the API endpoints required by the Loan Risk Assessment Dashboard frontend.

## � Quick Start

**Minimal setup to get started:**
1. Implement health check at `GET /health`
2. Implement file upload at `POST /applications/upload` 
3. Add CORS for `http://localhost:3000`
4. Return the expected JSON responses

**Frontend will detect your API automatically and switch from demo mode to live mode.**
## 📋 Table of Contents

1. [API Overview](#-api-overview)
2. [Required Endpoints](#️-required-endpoints)
3. [Authentication](#-authentication)
4. [CORS Configuration](#-cors-configuration)
5. [File Upload Implementation](#-file-upload-implementation)
6. [Database Schema](#-database-schema)
7. [Processing Pipeline](#-processing-pipeline)
8. [Testing Your API](#-testing-your-api)
9. [Performance Considerations](#-performance-considerations)
10. [Error Handling](#-error-handling)
11. [Security Recommendations](#-security-recommendations)
12. [Deployment](#-deployment)
## �🔌 API Overview

The frontend expects a RESTful API with the following base configuration:
- **Base URL**: `http://localhost:8000/api` (configurable via `VITE_API_BASE_URL`)
- **Content-Type**: `application/json` (except file uploads)
- **Authentication**: Bearer token support (optional)
- **CORS**: Required for development

## 🛠️ Required Endpoints

### 1. Health Check (Optional)
**GET** `/health`

Used to detect if backend is available.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-03-10T12:00:00Z"
}
```

### 2. Upload Application
**POST** `/applications/upload`

**Content-Type**: `multipart/form-data`

**Request Body:**
- `file`: PDF file (max 10MB)

**Response (201 Created):**
```json
{
  "application_id": "uuid-string",
  "status": "processing",
  "message": "Application uploaded successfully"
}
```

**Error Responses:**
```json
// File too large (413)
{
  "error": "File size exceeds 10MB limit",
  "code": "FILE_TOO_LARGE"
}

// Invalid file type (400)
{
  "error": "Only PDF files are allowed",
  "code": "INVALID_FILE_TYPE"
}

// Processing error (500)
{
  "error": "Failed to process document",
  "code": "PROCESSING_ERROR"
}
```

### 3. Check Processing Status
**GET** `/applications/{application_id}/status`

**Response (200 OK):**
```json
{
  "document_parsing": "completed|running|waiting|failed",
  "credit_analysis": "completed|running|waiting|failed", 
  "fraud_check": "completed|running|waiting|failed",
  "overall_status": "processing|completed|failed"
}
```

**Error Responses:**
```json
// Application not found (404)
{
  "error": "Application not found",
  "code": "APPLICATION_NOT_FOUND"
}
```

### 4. Get Analysis Result
**GET** `/applications/{application_id}/result`

**Response (200 OK):**
```json
{
  "credit_score": 720,
  "risk_category": "low|medium|high",
  "recommendation": "approve|reject|approve with conditions",
  "analysis_details": {
    "key_factors": [
      "Stable income source",
      "Good debt-to-income ratio",
      "Strong credit history"
    ],
    "risk_indicators": [
      "High credit utilization",
      "Recent credit inquiries"
    ],
    "positive_factors": [
      "Long credit history",
      "No missed payments in 24 months"
    ],
    "notes": "Strong application with minimal risk factors identified."
  },
  "processed_at": "2024-03-10T12:30:00Z"
}
```

**Error Responses:**
```json
// Analysis not ready (202)
{
  "error": "Analysis still in progress",
  "code": "ANALYSIS_PENDING"
}

// Analysis failed (422)
{
  "error": "Credit analysis failed",
  "code": "ANALYSIS_FAILED"
}
```

### 5. Get Application History
**GET** `/applications/history`

**Query Parameters:**
- `page`: Page number (default: 1)
- `limit`: Items per page (default: 10, max: 100)
- `status`: Filter by status (`completed|processing|failed`)
- `search`: Search by filename

**Response (200 OK):**
```json
{
  "applications": [
    {
      "id": "uuid-string",
      "filename": "loan_application_john_doe.pdf",
      "submitted_at": "2024-03-10T10:00:00Z",
      "status": "completed",
      "credit_score": 720,
      "risk_category": "low",
      "recommendation": "approve"
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 5,
    "total_items": 47,
    "items_per_page": 10
  }
}
```

### 6. Get Dashboard Stats (Optional)
**GET** `/dashboard/stats`

**Response (200 OK):**
```json
{
  "total_applications": 150,
  "pending_applications": 5,
  "completed_today": 12,
  "approval_rate": 68.5,
  "average_processing_time": 180
}
```

## 🔐 Authentication

The frontend supports Bearer token authentication. If your API requires authentication:

**Request Headers:**
```
Authorization: Bearer <jwt-token>
```

The frontend stores the token in `localStorage` as `auth_token`.

## 🌐 CORS Configuration

For development, ensure CORS is configured to allow:

```javascript
// Express.js example
app.use(cors({
  origin: ['http://localhost:3000', 'http://localhost:5173'],
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
}));
```

## 📁 File Upload Implementation

### Express.js Example
```javascript
const multer = require('multer');
const upload = multer({ 
  dest: 'uploads/',
  limits: { fileSize: 10 * 1024 * 1024 }, // 10MB
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') {
      cb(null, true);
    } else {
      cb(new Error('Only PDF files allowed'), false);
    }
  }
});

app.post('/api/applications/upload', upload.single('file'), (req, res) => {
  // File available as req.file
  // Generate application ID and start processing
  const applicationId = generateUUID();
  
  // Start async processing pipeline
  processApplication(applicationId, req.file);
  
  res.status(201).json({
    application_id: applicationId,
    status: 'processing'
  });
});
```

### FastAPI Example
```python
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/applications/upload")
async def upload_application(file: UploadFile = File(...)):
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files allowed")
    
    # Validate file size
    if file.size > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    
    application_id = str(uuid.uuid4())
    
    # Start processing
    await process_application_async(application_id, file)
    
    return {
        "application_id": application_id,
        "status": "processing"
    }
```

## 💾 Database Schema

### Applications Table
```sql
CREATE TABLE applications (
    id UUID PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500),
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'processing',
    credit_score INTEGER,
    risk_category VARCHAR(20),
    recommendation VARCHAR(100),
    analysis_details JSONB,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_submitted_at ON applications(submitted_at DESC);
```

### Processing Status Table
```sql
CREATE TABLE processing_status (
    application_id UUID REFERENCES applications(id),
    document_parsing VARCHAR(20) DEFAULT 'waiting',
    credit_analysis VARCHAR(20) DEFAULT 'waiting', 
    fraud_check VARCHAR(20) DEFAULT 'waiting',
    overall_status VARCHAR(20) DEFAULT 'processing',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🔄 Processing Pipeline

### Status Flow
```
waiting → running → completed
                 ↘ failed
```

### Implementation Example
```javascript
async function processApplication(applicationId, file) {
  try {
    // Update status: Document parsing started
    await updateStatus(applicationId, 'document_parsing', 'running');
    
    // 1. Parse PDF document
    const extractedData = await parsePDF(file);
    await updateStatus(applicationId, 'document_parsing', 'completed');
    
    // 2. Start credit analysis
    await updateStatus(applicationId, 'credit_analysis', 'running');
    const creditResult = await analyzeCreditRisk(extractedData);
    await updateStatus(applicationId, 'credit_analysis', 'completed');
    
    // 3. Start fraud check
    await updateStatus(applicationId, 'fraud_check', 'running');
    const fraudResult = await checkFraud(extractedData);
    await updateStatus(applicationId, 'fraud_check', 'completed');
    
    // 4. Generate final result
    const finalResult = await generateFinalAssessment(creditResult, fraudResult);
    
    // Save result and mark as completed
    await saveResult(applicationId, finalResult);
    await updateStatus(applicationId, 'overall_status', 'completed');
    
  } catch (error) {
    await updateStatus(applicationId, 'overall_status', 'failed');
    console.error('Processing failed:', error);
  }
}
```

## 🧪 Testing Your API

### Test with cURL
```bash
# Upload file
curl -X POST http://localhost:8000/api/applications/upload \
  -F "file=@sample.pdf" \
  -H "Authorization: Bearer your-token"

# Check status
curl http://localhost:8000/api/applications/{id}/status

# Get result
curl http://localhost:8000/api/applications/{id}/result

# Get history
curl "http://localhost:8000/api/applications/history?page=1&limit=10"
```

### Frontend Testing
1. Set `VITE_API_BASE_URL=http://localhost:8000/api` in `.env`
2. Start your backend server
3. Upload a PDF file through the frontend
4. Monitor the processing status updates

## ⚡ Performance Considerations

### File Storage
- Store uploaded files in cloud storage (AWS S3, Google Cloud Storage)
- Keep file metadata in database, not the files themselves
- Implement file cleanup after processing

### Processing Optimization
- Use background job queues (Redis, Celery, Bull)
- Implement rate limiting for uploads
- Add request timeout handling
- Consider async processing for long-running analysis

### Caching
- Cache frequently accessed data
- Use Redis for session storage
- Implement API response caching where appropriate

## 🚨 Error Handling

### Standard Error Response
```json
{
  "error": "Human readable error message",
  "code": "MACHINE_READABLE_CODE",
  "details": {
    "field": "Specific validation errors"
  },
  "timestamp": "2024-03-10T12:00:00Z"
}
```

### HTTP Status Codes
- `200` - Success
- `201` - Created (file upload)
- `400` - Bad Request (validation errors)
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `413` - Payload Too Large
- `422` - Unprocessable Entity (analysis failed)
- `429` - Too Many Requests
- `500` - Internal Server Error

## 🔒 Security Recommendations

1. **File Validation**:
   - Verify PDF magic bytes, not just MIME type
   - Scan uploads for malware
   - Limit file size (10MB recommended)

2. **Rate Limiting**:
   - Implement per-user upload limits
   - Add global rate limiting

3. **Authentication**:
   - Use JWT tokens with expiration
   - Implement refresh token mechanism
   - Add role-based access control

4. **Data Privacy**:
   - Encrypt sensitive data at rest
   - Log access to PII data
   - Implement data retention policies

## 🚀 Deployment

### Environment Variables
```bash
# Backend
DATABASE_URL=postgresql://user:pass@host:5432/loanrisk
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-secret-key
FILE_STORAGE_BUCKET=your-s3-bucket
MAX_FILE_SIZE=10485760

# Frontend
VITE_API_BASE_URL=https://api.yourdomain.com/api
```

### Health Check Endpoint
Recommended health check response:
```json
{
  "status": "healthy",
  "services": {
    "database": "connected",
    "redis": "connected",
    "storage": "connected"
  },
  "version": "1.0.0",
  "timestamp": "2024-03-10T12:00:00Z"
}
```

This guide provides everything needed to implement a backend that seamlessly integrates with the frontend dashboard. The frontend will automatically detect your API and switch from demo mode to live mode once your endpoints are available.

## 🛠️ Framework-Specific Tips

### Node.js/Express
- Use `multer` for file uploads
- Use `cors` middleware for CORS
- Consider `express-rate-limit` for rate limiting
- Use `joi` or `yup` for validation

### Python/FastAPI  
- Built-in file upload support with `UploadFile`
- Built-in CORS middleware
- Use `pydantic` for request/response validation
- Consider `celery` for background processing

### Python/Django
- Use `django-cors-headers` for CORS
- Use Django REST framework for API
- Consider `django-rq` or `celery` for async tasks
- Use `django-storages` for file storage

### Java/Spring Boot
- Use `@CrossOrigin` for CORS
- Use `MultipartFile` for uploads
- Consider Spring Cloud for microservices
- Use `@Async` for background processing

### .NET Core
- Use `IFormFile` for file uploads
- Configure CORS in `Startup.cs`
- Use `IHostedService` for background tasks
- Consider Azure Storage for files

---
**Need help?** This frontend includes comprehensive error handling and will provide clear feedback when your API endpoints aren't working as expected.