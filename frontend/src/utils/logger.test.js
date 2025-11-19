/**
 * Tests for logger utility
 */
import { logger } from './logger';

// Store original console methods
const originalConsole = {
  log: console.log,
  warn: console.warn,
  error: console.error,
  debug: console.debug,
  info: console.info
};

describe('logger', () => {
  beforeEach(() => {
    // Mock console methods
    console.log = vi.fn();
    console.warn = vi.fn();
    console.error = vi.fn();
    console.debug = vi.fn();
    console.info = vi.fn();
  });

  afterEach(() => {
    // Restore original console methods
    console.log = originalConsole.log;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
    console.debug = originalConsole.debug;
    console.info = originalConsole.info;
  });

  describe('log', () => {
    it('logs messages in development', () => {
      logger.log('test message');
      if (import.meta.env.DEV) {
        expect(console.log).toHaveBeenCalledWith('test message');
      }
    });

    it('logs multiple arguments', () => {
      logger.log('message', 123, { key: 'value' });
      if (import.meta.env.DEV) {
        expect(console.log).toHaveBeenCalledWith('message', 123, { key: 'value' });
      }
    });
  });

  describe('warn', () => {
    it('warns in development', () => {
      logger.warn('warning message');
      if (import.meta.env.DEV) {
        expect(console.warn).toHaveBeenCalledWith('warning message');
      }
    });

    it('warns with multiple arguments', () => {
      logger.warn('warning', 'details', { error: true });
      if (import.meta.env.DEV) {
        expect(console.warn).toHaveBeenCalledWith('warning', 'details', { error: true });
      }
    });
  });

  describe('error', () => {
    it('logs errors always (even in production)', () => {
      logger.error('error message');
      // Error should always be logged regardless of environment
      expect(console.error).toHaveBeenCalledWith('error message');
    });

    it('logs error with stack trace', () => {
      const error = new Error('test error');
      logger.error('Error occurred:', error);
      expect(console.error).toHaveBeenCalledWith('Error occurred:', error);
    });
  });

  describe('debug', () => {
    it('debugs in development', () => {
      logger.debug('debug message');
      if (import.meta.env.DEV) {
        expect(console.debug).toHaveBeenCalledWith('debug message');
      }
    });

    it('debugs with objects', () => {
      const obj = { foo: 'bar', nested: { key: 'value' } };
      logger.debug('object:', obj);
      if (import.meta.env.DEV) {
        expect(console.debug).toHaveBeenCalledWith('object:', obj);
      }
    });
  });

  describe('info', () => {
    it('logs info in development', () => {
      logger.info('info message');
      if (import.meta.env.DEV) {
        expect(console.info).toHaveBeenCalledWith('info message');
      }
    });

    it('logs info with multiple arguments', () => {
      logger.info('Information:', 'detail1', 'detail2');
      if (import.meta.env.DEV) {
        expect(console.info).toHaveBeenCalledWith('Information:', 'detail1', 'detail2');
      }
    });
  });
});
