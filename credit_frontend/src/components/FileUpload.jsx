import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File, X } from 'lucide-react';

const FileUpload = ({ onUpload, disabled, currentFile }) => {
  const onDrop = useCallback((acceptedFiles, rejectedFiles) => {
    if (rejectedFiles.length > 0) {
      const rejection = rejectedFiles[0];
      let errorMessage = 'File upload failed.';
      
      if (rejection.errors.some(error => error.code === 'file-invalid-type')) {
        errorMessage = 'Please upload a PDF file only.';
      } else if (rejection.errors.some(error => error.code === 'file-too-large')) {
        errorMessage = 'File size must be less than 10MB.';
      }
      
      // You can show an error message here if needed
      console.error(errorMessage);
      return;
    }

    const file = acceptedFiles[0];
    if (file && file.type === 'application/pdf') {
      onUpload(file);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf']
    },
    maxSize: 10 * 1024 * 1024, // 10MB
    multiple: false,
    disabled
  });

  if (currentFile && disabled) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="text-center">
          <h3 className="text-lg font-medium text-gray-900 mb-2">Processing Application</h3>
          <div className="flex items-center justify-center space-x-2 text-sm text-gray-600">
            <File className="h-4 w-4" />
            <span>{currentFile}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">Upload Loan Application</h3>
      
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors duration-200 ${
          isDragActive
            ? 'border-primary-400 bg-primary-50'
            : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <input {...getInputProps()} />
        
        <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
        
        {isDragActive ? (
          <div>
            <p className="text-lg text-primary-600 font-medium">Drop the PDF file here</p>
            <p className="text-sm text-gray-500 mt-1">Release to upload</p>
          </div>
        ) : (
          <div>
            <p className="text-lg text-gray-700 font-medium">
              Drag & drop a PDF file here, or click to select
            </p>
            <p className="text-sm text-gray-500 mt-1">
              Only PDF files are accepted (Max 10MB)
            </p>
          </div>
        )}
        
        <div className="mt-6">
          <button
            type="button"
            disabled={disabled}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
          >
            <Upload className="mr-2 h-4 w-4" />
            Select PDF File
          </button>
        </div>
      </div>
      
      <div className="mt-4 text-xs text-gray-500">
        <p>• Supported format: PDF only</p>
        <p>• Maximum file size: 10MB</p>
        <p>• The document will be automatically parsed and analyzed</p>
      </div>
    </div>
  );
};

export default FileUpload;