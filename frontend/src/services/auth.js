/**
 * Authentication service for AWS Cognito
 * Handles user login, token storage, and authentication state
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
} from 'amazon-cognito-identity-js';
import { logger } from '../utils/logger';

class AuthService {
  constructor() {
    this.tokenKey = 'cognito_id_token';
    this.refreshTokenKey = 'cognito_refresh_token';
    this.userKey = 'cognito_user';
    this.userPool = null;
    this.refreshTimer = null;
  }

  /**
   * Initialize Cognito configuration from runtime config
   */
  async init() {
    try {
      // Try to load runtime config from production deployment
      const configUrl = `${window.location.origin}/config.json`;
      const response = await fetch(configUrl, {
        // Don't show fetch errors in console for 404 (normal in dev)
        cache: 'no-cache'
      });

      if (!response.ok) {
        // In development, config.json won't exist - this is expected
        if (response.status === 404) {
          throw new Error('Config file not found (expected in local development)');
        }
        throw new Error(`Failed to load config: ${response.status}`);
      }

      const config = await response.json();

      this.cognitoConfig = {
        userPoolId: config.cognitoUserPoolId,
        clientId: config.cognitoClientId,
        region: config.cognitoRegion,
        domain: config.cognitoDomain,
      };

      // Also store the API URL from config
      this.apiBaseUrl = config.apiUrl;

      // Initialize Cognito User Pool
      this.initUserPool();

      logger.log('Loaded Cognito configuration from /config.json');
      return this.cognitoConfig;
    } catch (error) {
      // Fallback to environment variables for local development
      // This is the expected path when running locally
      const isDev = import.meta.env.DEV;
      if (isDev || error.message.includes('not found')) {
        logger.log('Using Cognito configuration from environment variables (local development)');
      } else {
        logger.warn('Failed to load /config.json, using environment variables:', error.message);
      }

      this.cognitoConfig = {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
        region: import.meta.env.VITE_COGNITO_REGION || 'us-east-1',
        domain: import.meta.env.VITE_COGNITO_DOMAIN,
      };

      // Also use API URL from environment for local dev
      this.apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

      // Initialize Cognito User Pool
      this.initUserPool();

      return this.cognitoConfig;
    }
  }

  /**
   * Initialize the Cognito User Pool
   */
  initUserPool() {
    if (this.cognitoConfig?.userPoolId && this.cognitoConfig?.clientId) {
      this.userPool = new CognitoUserPool({
        UserPoolId: this.cognitoConfig.userPoolId,
        ClientId: this.cognitoConfig.clientId,
      });
    }
  }

  /**
   * Check if Cognito is configured
   */
  isConfigured() {
    return !!(
      this.cognitoConfig?.userPoolId &&
      this.cognitoConfig?.clientId &&
      this.cognitoConfig?.domain
    );
  }

  /**
   * Authenticate user with email and password (direct authentication)
   */
  async authenticateUser(email, password) {
    return new Promise((resolve, reject) => {
      if (!this.userPool) {
        reject(new Error('User pool not initialized'));
        return;
      }

      const authenticationDetails = new AuthenticationDetails({
        Username: email,
        Password: password,
      });

      const cognitoUser = new CognitoUser({
        Username: email,
        Pool: this.userPool,
      });

      cognitoUser.authenticateUser(authenticationDetails, {
        onSuccess: (result) => {
          const idToken = result.getIdToken().getJwtToken();
          const refreshToken = result.getRefreshToken().getToken();

          // Store both tokens
          this.setToken(idToken);
          this.setRefreshToken(refreshToken);

          // Schedule token refresh
          this.scheduleTokenRefresh(result.getIdToken());

          resolve({ success: true, idToken });
        },
        onFailure: (err) => {
          reject(err);
        },
        newPasswordRequired: (userAttributes, requiredAttributes) => {
          // Handle new password required scenario
          reject(new Error('New password required. Please contact administrator.'));
        },
      });
    });
  }

  /**
   * Get the Cognito hosted UI login URL
   */
  getLoginUrl() {
    if (!this.cognitoConfig) {
      throw new Error('Auth service not initialized');
    }

    if (!this.isConfigured()) {
      throw new Error('Cognito is not configured. Please set environment variables or deploy config.json');
    }

    const redirectUri = window.location.origin;
    const { domain, clientId } = this.cognitoConfig;

    return `https://${domain}/login?client_id=${clientId}&response_type=token&scope=email+openid+profile&redirect_uri=${encodeURIComponent(redirectUri)}`;
  }

  /**
   * Get the Cognito hosted UI logout URL
   */
  getLogoutUrl() {
    if (!this.cognitoConfig) {
      throw new Error('Auth service not initialized');
    }

    const redirectUri = window.location.origin;
    const { domain, clientId } = this.cognitoConfig;

    return `https://${domain}/logout?client_id=${clientId}&logout_uri=${encodeURIComponent(redirectUri)}`;
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated() {
    const token = this.getToken();
    if (!token) return false;

    // Check if token is expired
    try {
      const payload = this.parseJwt(token);
      const now = Date.now() / 1000;
      return payload.exp > now;
    } catch {
      return false;
    }
  }

  /**
   * Parse JWT token (without verification - verification happens on backend)
   */
  parseJwt(token) {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  }

  /**
   * Get stored token
   */
  getToken() {
    return localStorage.getItem(this.tokenKey);
  }

  /**
   * Store token
   */
  setToken(token) {
    localStorage.setItem(this.tokenKey, token);
  }

  /**
   * Get stored refresh token
   */
  getRefreshToken() {
    return localStorage.getItem(this.refreshTokenKey);
  }

  /**
   * Store refresh token
   */
  setRefreshToken(token) {
    localStorage.setItem(this.refreshTokenKey, token);
  }

  /**
   * Get stored user info
   */
  getUser() {
    const userJson = localStorage.getItem(this.userKey);
    return userJson ? JSON.parse(userJson) : null;
  }

  /**
   * Store user info
   */
  setUser(user) {
    localStorage.setItem(this.userKey, JSON.stringify(user));
  }

  /**
   * Clear authentication data
   */
  clearAuth() {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.refreshTokenKey);
    localStorage.removeItem(this.userKey);
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  /**
   * Handle OAuth redirect callback
   * Extracts token from URL hash and stores it
   * Note: OAuth hosted UI flow doesn't provide refresh tokens in URL,
   * so we can't set up auto-refresh for this flow
   */
  handleCallback() {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const idToken = params.get('id_token');
    const accessToken = params.get('access_token');

    if (idToken) {
      this.setToken(idToken);

      // Note: Refresh token is not available in OAuth hosted UI redirect
      // User will need to re-login after token expires (typically 1 hour)
      // To get refresh tokens, use direct authentication (authenticateUser method)

      // Parse user info from token
      try {
        const payload = this.parseJwt(idToken);
        this.setUser({
          email: payload.email,
          sub: payload.sub,
          groups: payload['cognito:groups'] || [],
        });

        // Schedule token refresh (though it won't work without refresh token)
        this.scheduleTokenRefresh({ getJwtToken: () => idToken });
      } catch (error) {
        logger.error('Failed to parse token:', error);
      }

      // Clean up URL
      window.history.replaceState(null, null, window.location.pathname);

      return true;
    }

    return false;
  }

  /**
   * Login - redirect to Cognito hosted UI
   */
  async login() {
    if (!this.cognitoConfig) {
      await this.init();
    }
    window.location.href = this.getLoginUrl();
  }

  /**
   * Logout - clear local storage and optionally redirect to Cognito logout
   */
  async logout(redirectToCognito = false) {
    this.clearAuth();

    if (redirectToCognito && this.cognitoConfig) {
      window.location.href = this.getLogoutUrl();
    } else {
      // Just reload the page to clear state
      window.location.reload();
    }
  }

  /**
   * Get current user from backend
   */
  async getCurrentUser() {
    const token = this.getToken();
    if (!token) {
      return { authenticated: false, user: null };
    }

    // Ensure we have initialized
    if (!this.cognitoConfig) {
      await this.init();
    }

    // Use stored API URL from config
    const apiUrl = this.apiBaseUrl || import.meta.env.VITE_API_URL || 'http://localhost:8000';

    try {
      const response = await fetch(`${apiUrl}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        // Token might be invalid or expired
        this.clearAuth();
        return { authenticated: false, user: null };
      }

      const data = await response.json();

      if (data.authenticated && data.user) {
        this.setUser(data.user);
      }

      return data;
    } catch (error) {
      logger.error('Failed to get current user:', error);
      return { authenticated: false, user: null };
    }
  }

  /**
   * Check if user is admin
   */
  isAdmin() {
    const user = this.getUser();
    return user?.is_admin || user?.groups?.includes('admins') || false;
  }

  /**
   * Schedule automatic token refresh
   * Refreshes 5 minutes before expiration
   */
  scheduleTokenRefresh(idToken) {
    // Clear any existing timer
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
    }

    try {
      const payload = this.parseJwt(idToken.getJwtToken());
      const expiresAt = payload.exp * 1000; // Convert to milliseconds
      const now = Date.now();
      const timeUntilExpiry = expiresAt - now;

      // Refresh 5 minutes before expiration (or immediately if already expired)
      const refreshTime = Math.max(0, timeUntilExpiry - 5 * 60 * 1000);

      logger.log(`Token refresh scheduled in ${Math.round(refreshTime / 1000 / 60)} minutes`);

      this.refreshTimer = setTimeout(() => {
        this.refreshSession();
      }, refreshTime);
    } catch (error) {
      logger.error('Failed to schedule token refresh:', error);
    }
  }

  /**
   * Refresh the current session using refresh token
   */
  async refreshSession() {
    return new Promise((resolve, reject) => {
      if (!this.userPool) {
        logger.warn('Cannot refresh session: user pool not initialized');
        reject(new Error('User pool not initialized'));
        return;
      }

      const refreshToken = this.getRefreshToken();
      if (!refreshToken) {
        logger.warn('No refresh token available');
        reject(new Error('No refresh token available'));
        return;
      }

      const user = this.getUser();
      if (!user || !user.email) {
        logger.warn('No user email available for refresh');
        reject(new Error('No user information available'));
        return;
      }

      const cognitoUser = new CognitoUser({
        Username: user.email,
        Pool: this.userPool,
      });

      const { CognitoRefreshToken } = require('amazon-cognito-identity-js');
      const token = new CognitoRefreshToken({ RefreshToken: refreshToken });

      cognitoUser.refreshSession(token, (err, session) => {
        if (err) {
          logger.error('Token refresh failed:', err);
          // Clear auth and force re-login
          this.clearAuth();
          reject(err);
          return;
        }

        const idToken = session.getIdToken().getJwtToken();
        const newRefreshToken = session.getRefreshToken().getToken();

        // Update stored tokens
        this.setToken(idToken);
        this.setRefreshToken(newRefreshToken);

        // Schedule next refresh
        this.scheduleTokenRefresh(session.getIdToken());

        logger.log('Token refreshed successfully');
        resolve({ success: true, idToken });
      });
    });
  }

  /**
   * Initialize automatic token refresh on app start
   * Call this when the app loads to set up auto-refresh
   */
  initializeAutoRefresh() {
    const token = this.getToken();
    if (!token) return;

    try {
      const payload = this.parseJwt(token);
      const now = Date.now() / 1000;

      // If token is expired, try to refresh immediately
      if (payload.exp <= now) {
        logger.log('Token expired, attempting refresh...');
        this.refreshSession().catch(() => {
          logger.warn('Auto-refresh failed, user needs to log in again');
        });
      } else {
        // Token is still valid, schedule refresh before expiration
        this.scheduleTokenRefresh({ getJwtToken: () => token });
      }
    } catch (error) {
      logger.error('Failed to initialize auto-refresh:', error);
    }
  }
}

export default new AuthService();