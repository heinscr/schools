/**
 * Tests for formatting utilities
 */
import { formatCurrency, normalizeTownName } from './formatters';

describe('formatCurrency', () => {
  it('formats positive numbers correctly', () => {
    expect(formatCurrency(1234.56)).toBe('$1,234.56');
    expect(formatCurrency(100)).toBe('$100.00');
    expect(formatCurrency(0.99)).toBe('$0.99');
  });

  it('formats large numbers with commas', () => {
    expect(formatCurrency(1000000)).toBe('$1,000,000.00');
    expect(formatCurrency(123456.78)).toBe('$123,456.78');
  });

  it('formats zero correctly', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });

  it('formats negative numbers correctly', () => {
    expect(formatCurrency(-50.25)).toBe('$-50.25');
    expect(formatCurrency(-1234.56)).toBe('$-1,234.56');
  });

  it('handles string numbers', () => {
    expect(formatCurrency('1234.56')).toBe('$1,234.56');
    expect(formatCurrency('100')).toBe('$100.00');
  });

  it('handles decimal precision correctly', () => {
    expect(formatCurrency(10.5)).toBe('$10.50');
    expect(formatCurrency(10.123)).toBe('$10.12'); // Should round to 2 decimals
    expect(formatCurrency(10.999)).toBe('$11.00'); // Should round up
  });

  it('handles null and undefined values', () => {
    expect(formatCurrency(null)).toBe('N/A');
    expect(formatCurrency(undefined)).toBe('N/A');
  });

  it('handles very small numbers', () => {
    expect(formatCurrency(0.01)).toBe('$0.01');
    expect(formatCurrency(0.001)).toBe('$0.00'); // Rounds to 2 decimals
  });
});

describe('normalizeTownName', () => {
  it('converts to lowercase', () => {
    expect(normalizeTownName('BOSTON')).toBe('boston');
    expect(normalizeTownName('Cambridge')).toBe('cambridge');
  });

  it('trims whitespace', () => {
    expect(normalizeTownName('  Boston  ')).toBe('boston');
    expect(normalizeTownName('\tCambridge\n')).toBe('cambridge');
  });

  it('handles mixed case and whitespace', () => {
    expect(normalizeTownName('  New BEDFORD  ')).toBe('new bedford');
  });

  it('handles empty string', () => {
    expect(normalizeTownName('')).toBe('');
  });

  it('handles null and undefined', () => {
    expect(normalizeTownName(null)).toBe('');
    expect(normalizeTownName(undefined)).toBe('');
  });

  it('handles numbers as input', () => {
    expect(normalizeTownName(123)).toBe('123');
  });

  it('preserves internal spaces', () => {
    expect(normalizeTownName('New Bedford')).toBe('new bedford');
    expect(normalizeTownName('Martha\'s Vineyard')).toBe('martha\'s vineyard');
  });
});
