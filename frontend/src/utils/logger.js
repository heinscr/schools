/**
 * Logger utility for development-safe console logging
 * In production, only errors are logged to avoid performance overhead
 */

const isDev = import.meta.env.DEV;

export const logger = {
  /**
   * Log informational messages (development only)
   */
  log: (...args) => {
    if (isDev) {
      console.log(...args);
    }
  },

  /**
   * Log warning messages (development only)
   */
  warn: (...args) => {
    if (isDev) {
      console.warn(...args);
    }
  },

  /**
   * Log error messages (always logged)
   */
  error: (...args) => {
    console.error(...args);
  },

  /**
   * Log debug messages (development only)
   */
  debug: (...args) => {
    if (isDev) {
      console.debug(...args);
    }
  },

  /**
   * Log informational messages (development only, with special formatting)
   */
  info: (...args) => {
    if (isDev) {
      console.info(...args);
    }
  }
};
