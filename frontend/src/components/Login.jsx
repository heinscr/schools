import { useState, useEffect } from 'react';
import authService from '../services/auth';
import './Login.css';

function Login({ onAuthChange, onLoadingChange }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false); // Start false, only show during callback
  const [showMenu, setShowMenu] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [cognitoConfigured, setCognitoConfigured] = useState(false);
  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [loginError, setLoginError] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  useEffect(() => {
    initAuth();
  }, []);

  // Notify parent component of loading state changes
  useEffect(() => {
    if (onLoadingChange) {
      onLoadingChange(loading);
    }
  }, [loading, onLoadingChange]);

  const initAuth = async () => {
    try {
      // Initialize auth service
      await authService.init();

      // Check if Cognito is properly configured
      setCognitoConfigured(authService.isConfigured());

      if (!authService.isConfigured()) {
        console.warn('Cognito is not configured. Authentication features will be disabled.');
        return;
      }

      // Check for OAuth callback
      const hasCallback = authService.handleCallback();

      if (hasCallback) {
        // Show loading modal during callback processing
        setLoading(true);
        // If we just completed authentication, fetch user details
        await fetchUserDetails();
      } else if (authService.isAuthenticated()) {
        // If already authenticated, fetch user details (no loading modal)
        await fetchUserDetails();
      }
    } catch (error) {
      console.error('Auth initialization error:', error);
      setLoading(false);
    }
  };

  const fetchUserDetails = async () => {
    try {
      const authData = await authService.getCurrentUser();

      if (authData.authenticated) {
        setUser(authData.user);
        if (onAuthChange) {
          onAuthChange(authData.user);
        }
      }
    } catch (error) {
      console.error('Failed to fetch user details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = () => {
    setShowLoginModal(true);
    setLoginError('');
  };

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setLoginError('');
    setIsLoggingIn(true);

    try {
      await authService.authenticateUser(loginForm.email, loginForm.password);
      await fetchUserDetails();
      setShowLoginModal(false);
      setLoginForm({ email: '', password: '' });
    } catch (error) {
      console.error('Login error:', error);
      setLoginError(error.message || 'Login failed. Please check your credentials.');
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleCloseModal = () => {
    setShowLoginModal(false);
    setLoginError('');
    setLoginForm({ email: '', password: '' });
  };

  const handleLogout = () => {
    authService.logout(false);
    setUser(null);
    if (onAuthChange) {
      onAuthChange(null);
    }
  };

  const toggleMenu = () => {
    setShowMenu(!showMenu);
  };

  // Don't render the loading overlay here - parent handles it
  if (loading) {
    return null;
  }

  // Don't show login button if Cognito is not configured
  if (!cognitoConfigured) {
    return null;
  }

  if (!user) {
    return (
      <>
        <button className="login-icon-button" onClick={handleLogin} title="Login">
          <svg className="user-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="10" r="3" />
            <path d="M6.168 18.849A4 4 0 0 1 10 16h4a4 4 0 0 1 3.834 2.855" />
          </svg>
        </button>

        {showLoginModal && (
          <div className="login-modal-backdrop" onClick={handleCloseModal}>
            <div className="login-modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="login-modal-header">
                <h2>Login</h2>
                <button className="login-modal-close" onClick={handleCloseModal}>×</button>
              </div>
              
              <form onSubmit={handleLoginSubmit} className="login-form">
                {loginError && <div className="login-error">{loginError}</div>}
                
                <div className="login-form-group">
                  <label htmlFor="email">Email</label>
                  <input
                    type="email"
                    id="email"
                    value={loginForm.email}
                    onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })}
                    required
                    autoFocus
                    disabled={isLoggingIn}
                  />
                </div>

                <div className="login-form-group">
                  <label htmlFor="password">Password</label>
                  <input
                    type="password"
                    id="password"
                    value={loginForm.password}
                    onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                    required
                    disabled={isLoggingIn}
                  />
                </div>

                <button type="submit" className="login-submit-button" disabled={isLoggingIn}>
                  {isLoggingIn ? 'Logging in...' : 'Login'}
                </button>
              </form>
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="user-menu">
      <button className="user-icon-button logged-in" onClick={toggleMenu} title={user.email}>
        <svg className="user-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <circle cx="12" cy="10" r="3" />
          <path d="M6.168 18.849A4 4 0 0 1 10 16h4a4 4 0 0 1 3.834 2.855" />
        </svg>
        {user.is_admin && <span className="admin-dot"></span>}
      </button>

      {showMenu && (
        <div className="user-dropdown">
          <div className="user-info">
            <div className="user-info-email">{user.email}</div>
            {user.is_admin && <div className="user-info-role">Administrator</div>}
          </div>
          <hr />
          <button className="logout-button" onClick={handleLogout}>
            Logout
          </button>
        </div>
      )}
    </div>
  );
}

export default Login;
