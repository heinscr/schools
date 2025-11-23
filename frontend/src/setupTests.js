import '@testing-library/jest-dom';
import { vi } from 'vitest';
import React from 'react';

// Mock ContractPdfModal to avoid react-pdf issues in tests
vi.mock('./components/ContractPdfModal', () => ({
  default: ({ districtName, pdfUrl, onClose }) => {
    return React.createElement('div', { 'data-testid': 'contract-pdf-modal' },
      React.createElement('div', null, districtName + ' - Contract'),
      React.createElement('div', null, pdfUrl),
      React.createElement('button', { onClick: onClose }, 'Close')
    );
  }
}));
