/**
 * Tests for authentication service
 */
import AuthService from './auth';

// Mock localStorage
const mockLocalStorage = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = value; },
    removeItem: (key) => { delete store[key]; },
    clear: () => { store = {}; }
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage
});

// Mock logger
vi.mock('../utils/logger', () => ({
  logger: {
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  }
}));

const originalFetch = global.fetch;

describe('AuthService', () => {
  beforeEach(() => {
    mockLocalStorage.clear();
    global.fetch = vi.fn();
    // Reset auth service state
    AuthService.cognitoConfig = null;
    AuthService.userPool = null;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('init', () => {
    it('loads config from /config.json when available', async () => {
      const mockConfig = {
        cognitoUserPoolId: 'us-east-1_POOL123',
        cognitoClientId: 'client123',
        cognitoRegion: 'us-east-1',
        cognitoDomain: 'test.auth.us-east-1.amazoncognito.com',
        apiUrl: 'https://api.example.com'
      };

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockConfig
      });

      const config = await AuthService.init();

      expect(config.userPoolId).toBe('us-east-1_POOL123');
      expect(config.clientId).toBe('client123');
      expect(AuthService.apiBaseUrl).toBe('https://api.example.com');
    });

    it('falls back to environment variables when config.json not found', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 404
      });

      const config = await AuthService.init();

      // Should use environment variables (or undefined in test environment)
      // The config will exist but values may be undefined
      expect(config).toBeDefined();
      expect(config.region).toBeDefined(); // Has default value
    });

    it('falls back to environment variables on fetch error', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      const config = await AuthService.init();

      // Should use environment variables (or undefined in test environment)
      expect(config).toBeDefined();
      expect(config.region).toBeDefined(); // Has default value
    });
  });

  describe('isConfigured', () => {
    it('returns true when all required config is present', () => {
      AuthService.cognitoConfig = {
        userPoolId: 'pool-123',
        clientId: 'client-123',
        domain: 'test.auth.amazoncognito.com'
      };

      expect(AuthService.isConfigured()).toBe(true);
    });

    it('returns false when config is missing', () => {
      AuthService.cognitoConfig = null;
      expect(AuthService.isConfigured()).toBe(false);
    });

    it('returns false when required fields are missing', () => {
      AuthService.cognitoConfig = {
        userPoolId: 'pool-123',
        clientId: 'client-123'
        // domain is missing
      };

      expect(AuthService.isConfigured()).toBe(false);
    });
  });

  describe('token management', () => {
    it('stores and retrieves token', () => {
      const token = 'test-jwt-token';
      AuthService.setToken(token);

      expect(AuthService.getToken()).toBe(token);
    });

    it('returns null when no token stored', () => {
      expect(AuthService.getToken()).toBeNull();
    });

    it('clears token', () => {
      AuthService.setToken('test-token');
      AuthService.clearAuth();

      expect(AuthService.getToken()).toBeNull();
    });
  });

  describe('user management', () => {
    it('stores and retrieves user', () => {
      const user = {
        email: 'test@example.com',
        sub: 'user-123',
        groups: ['users']
      };

      AuthService.setUser(user);
      const retrieved = AuthService.getUser();

      expect(retrieved.email).toBe('test@example.com');
      expect(retrieved.sub).toBe('user-123');
    });

    it('returns null when no user stored', () => {
      expect(AuthService.getUser()).toBeNull();
    });

    it('clears user', () => {
      AuthService.setUser({ email: 'test@example.com' });
      AuthService.clearAuth();

      expect(AuthService.getUser()).toBeNull();
    });
  });

  describe('parseJwt', () => {
    it('parses valid JWT token', () => {
      // Create a simple JWT (header.payload.signature)
      const payload = { sub: 'user-123', exp: 9999999999 };
      const encodedPayload = btoa(JSON.stringify(payload));
      const token = `header.${encodedPayload}.signature`;

      const parsed = AuthService.parseJwt(token);

      expect(parsed.sub).toBe('user-123');
      expect(parsed.exp).toBe(9999999999);
    });

    it('handles URL-safe base64', () => {
      const payload = { test: 'data' };
      const jsonString = JSON.stringify(payload);
      // Use URL-safe base64
      const encodedPayload = btoa(jsonString).replace(/\+/g, '-').replace(/\//g, '_');
      const token = `header.${encodedPayload}.signature`;

      const parsed = AuthService.parseJwt(token);
      expect(parsed.test).toBe('data');
    });
  });

  describe('isAuthenticated', () => {
    it('returns false when no token', () => {
      expect(AuthService.isAuthenticated()).toBe(false);
    });

    it('returns true for valid non-expired token', () => {
      const futureTimestamp = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now
      const payload = { exp: futureTimestamp };
      const encodedPayload = btoa(JSON.stringify(payload));
      const token = `header.${encodedPayload}.signature`;

      AuthService.setToken(token);

      expect(AuthService.isAuthenticated()).toBe(true);
    });

    it('returns false for expired token', () => {
      const pastTimestamp = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      const payload = { exp: pastTimestamp };
      const encodedPayload = btoa(JSON.stringify(payload));
      const token = `header.${encodedPayload}.signature`;

      AuthService.setToken(token);

      expect(AuthService.isAuthenticated()).toBe(false);
    });

    it('returns false for invalid token format', () => {
      AuthService.setToken('invalid-token');

      expect(AuthService.isAuthenticated()).toBe(false);
    });
  });

  describe('getLoginUrl', () => {
    it('generates correct login URL', () => {
      AuthService.cognitoConfig = {
        userPoolId: 'pool-123',
        domain: 'test.auth.us-east-1.amazoncognito.com',
        clientId: 'client-123'
      };

      const url = AuthService.getLoginUrl();

      expect(url).toContain('https://test.auth.us-east-1.amazoncognito.com/login');
      expect(url).toContain('client_id=client-123');
      expect(url).toContain('response_type=token');
      expect(url).toContain('scope=email+openid+profile');
    });

    it('throws error when not initialized', () => {
      AuthService.cognitoConfig = null;

      expect(() => AuthService.getLoginUrl()).toThrow('not initialized');
    });

    it('throws error when not configured', () => {
      AuthService.cognitoConfig = {
        userPoolId: 'pool-123'
        // missing domain and clientId
      };

      expect(() => AuthService.getLoginUrl()).toThrow('not configured');
    });
  });

  describe('getLogoutUrl', () => {
    it('generates correct logout URL', () => {
      AuthService.cognitoConfig = {
        domain: 'test.auth.us-east-1.amazoncognito.com',
        clientId: 'client-123'
      };

      const url = AuthService.getLogoutUrl();

      expect(url).toContain('https://test.auth.us-east-1.amazoncognito.com/logout');
      expect(url).toContain('client_id=client-123');
      expect(url).toContain('logout_uri=');
    });

    it('throws error when not initialized', () => {
      AuthService.cognitoConfig = null;

      expect(() => AuthService.getLogoutUrl()).toThrow('not initialized');
    });
  });

  describe('handleCallback', () => {
    const originalLocation = window.location;

    beforeEach(() => {
      delete window.location;
      window.location = {
        hash: '',
        pathname: '/test',
        href: 'http://localhost'
      };
      window.history = {
        replaceState: vi.fn()
      };
    });

    afterEach(() => {
      window.location = originalLocation;
    });

    it('extracts token from URL hash', () => {
      const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwiY29nbml0bzpncm91cHMiOlsidXNlcnMiXX0.signature';
      window.location.hash = `#id_token=${token}&access_token=access-token`;

      const result = AuthService.handleCallback();

      expect(result).toBe(true);
      expect(AuthService.getToken()).toBe(token);
    });

    it('returns false when no token in hash', () => {
      window.location.hash = '';

      const result = AuthService.handleCallback();

      expect(result).toBe(false);
      expect(AuthService.getToken()).toBeNull();
    });

    it('cleans up URL after extracting token', () => {
      const token = 'test-token-with-payload.eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20ifQ.sig';
      window.location.hash = `#id_token=${token}`;

      AuthService.handleCallback();

      expect(window.history.replaceState).toHaveBeenCalled();
    });
  });

  describe('getCurrentUser', () => {
    beforeEach(() => {
      AuthService.cognitoConfig = {
        userPoolId: 'pool-123',
        clientId: 'client-123',
        domain: 'test.auth.amazoncognito.com'
      };
      AuthService.apiBaseUrl = 'https://api.example.com';
    });

    it('returns unauthenticated when no token', async () => {
      const result = await AuthService.getCurrentUser();

      expect(result.authenticated).toBe(false);
      expect(result.user).toBeNull();
    });

    it('fetches user from backend with valid token', async () => {
      AuthService.setToken('valid-token');

      const mockResponse = {
        authenticated: true,
        user: {
          email: 'test@example.com',
          username: 'testuser',
          is_admin: false,
          groups: ['users']
        }
      };

      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const result = await AuthService.getCurrentUser();

      expect(result.authenticated).toBe(true);
      expect(result.user.email).toBe('test@example.com');
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/api/auth/me',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer valid-token'
          })
        })
      );
    });

    it('clears auth on 401 response', async () => {
      AuthService.setToken('invalid-token');

      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401
      });

      const result = await AuthService.getCurrentUser();

      expect(result.authenticated).toBe(false);
      expect(AuthService.getToken()).toBeNull();
    });

    it('handles network errors gracefully', async () => {
      AuthService.setToken('valid-token');

      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      const result = await AuthService.getCurrentUser();

      expect(result.authenticated).toBe(false);
    });
  });

  describe('isAdmin', () => {
    it('returns true for admin user with is_admin flag', () => {
      AuthService.setUser({
        email: 'admin@example.com',
        is_admin: true
      });

      expect(AuthService.isAdmin()).toBe(true);
    });

    it('returns true for user in admins group', () => {
      AuthService.setUser({
        email: 'admin@example.com',
        groups: ['admins', 'users']
      });

      expect(AuthService.isAdmin()).toBe(true);
    });

    it('returns false for non-admin user', () => {
      AuthService.setUser({
        email: 'user@example.com',
        is_admin: false,
        groups: ['users']
      });

      expect(AuthService.isAdmin()).toBe(false);
    });

    it('returns false when no user', () => {
      expect(AuthService.isAdmin()).toBe(false);
    });
  });
});
