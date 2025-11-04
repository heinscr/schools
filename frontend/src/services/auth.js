/**
 * Authentication service for AWS Cognito
 * Handles user login, token storage, and authentication state
 */

class AuthService {
  constructor() {
    this.tokenKey = 'cognito_id_token';
    this.userKey = 'cognito_user';
  }

  /**
   * Initialize Cognito configuration from runtime config
   */
  async init() {
    try {
      const response = await fetch('/config.json');
      const config = await response.json();

      this.cognitoConfig = {
        userPoolId: config.cognitoUserPoolId,
        clientId: config.cognitoClientId,
        region: config.cognitoRegion,
        domain: config.cognitoDomain,
      };

      return this.cognitoConfig;
    } catch (error) {
      console.error('Failed to load Cognito configuration:', error);
      // Fallback to environment variables for local development
      this.cognitoConfig = {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
        region: import.meta.env.VITE_COGNITO_REGION || 'us-east-1',
        domain: import.meta.env.VITE_COGNITO_DOMAIN,
      };
      return this.cognitoConfig;
    }
  }

  /**
   * Get the Cognito hosted UI login URL
   */
  getLoginUrl() {
    if (!this.cognitoConfig) {
      throw new Error('Auth service not initialized');
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
    localStorage.removeItem(this.userKey);
  }

  /**
   * Handle OAuth redirect callback
   * Extracts token from URL hash and stores it
   */
  handleCallback() {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const idToken = params.get('id_token');
    const accessToken = params.get('access_token');

    if (idToken) {
      this.setToken(idToken);

      // Parse user info from token
      try {
        const payload = this.parseJwt(idToken);
        this.setUser({
          email: payload.email,
          sub: payload.sub,
          groups: payload['cognito:groups'] || [],
        });
      } catch (error) {
        console.error('Failed to parse token:', error);
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
  async getCurrentUser(apiBaseUrl) {
    const token = this.getToken();
    if (!token) {
      return { authenticated: false, user: null };
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/me`, {
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
      console.error('Failed to get current user:', error);
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
}

export default new AuthService();
