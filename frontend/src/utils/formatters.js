/**
 * Formatting utilities for consistent data display
 */

/**
 * Format a number as USD currency with 2 decimal places
 * @param {number|string} value - The value to format
 * @returns {string} - Formatted currency string (e.g., "$12,345.67")
 */
export const formatCurrency = (value) => {
  if (value === null || value === undefined) return 'N/A';
  return `$${Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
};

/**
 * Normalize town name for consistent comparison
 * @param {string|null|undefined} townName - Raw town name
 * @returns {string} - Normalized town name (lowercase, trimmed)
 */
export const normalizeTownName = (townName) => {
  if (!townName) return '';
  return String(townName).trim().toLowerCase();
};
