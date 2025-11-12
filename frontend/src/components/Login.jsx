import { useState, useEffect } from 'react';
import authService from '../services/auth';
import api from '../services/api';
import { logger } from '../utils/logger';
import BackupManager from './BackupManager';
import ConfirmDialog from './ConfirmDialog';
import Toast from './Toast';
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
  const [normalizationStatus, setNormalizationStatus] = useState(null);
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [showBackupManager, setShowBackupManager] = useState(false);
  const [showNormalizeConfirm, setShowNormalizeConfirm] = useState(false);
  const [toast, setToast] = useState({ isOpen: false, message: '', variant: 'success' });

  useEffect(() => {
    initAuth();
  }, []);

  // Notify parent component of loading state changes
  useEffect(() => {
    if (onLoadingChange) {
      onLoadingChange(loading);
    }
  }, [loading, onLoadingChange]);

  // Poll for normalization status if user is admin
  useEffect(() => {
    if (!user || !user.is_admin) {
      setNormalizationStatus(null);
      return;
    }

    const checkNormalizationStatus = async () => {
      try {
        const status = await api.getNormalizationStatus();
        setNormalizationStatus(status);
      } catch (err) {
        logger.warn('Failed to check normalization status:', err);
      }
    };

    // Check immediately
    checkNormalizationStatus();

    // Poll every 30 seconds
    const interval = setInterval(checkNormalizationStatus, 30000);

    return () => clearInterval(interval);
  }, [user]);

  const initAuth = async () => {
    try {
      // Initialize auth service
      await authService.init();

      // Check if Cognito is properly configured
      setCognitoConfigured(authService.isConfigured());

      if (!authService.isConfigured()) {
        logger.warn('Cognito is not configured. Authentication features will be disabled.');
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
      logger.error('Auth initialization error:', error);
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
      logger.error('Failed to fetch user details:', error);
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
      logger.error('Login error:', error);
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

  const handleNormalize = () => {
    if (isNormalizing) return;
    setShowNormalizeConfirm(true);
  };

  const confirmNormalize = async () => {
    setShowNormalizeConfirm(false);

    try {
      setIsNormalizing(true);
      await api.startNormalization();
      setToast({
        isOpen: true,
        message: 'Normalization started successfully. This will take a few minutes to complete.',
        variant: 'success'
      });
      setShowMenu(false);

      // Check status immediately
      const status = await api.getNormalizationStatus();
      setNormalizationStatus(status);
    } catch (err) {
      setToast({
        isOpen: true,
        message: `Failed to start normalization: ${err.message}`,
        variant: 'error'
      });
    } finally {
      setIsNormalizing(false);
    }
  };

  const handleOpenBackupManager = () => {
    setShowBackupManager(true);
    setShowMenu(false);
  };

  const handleCloseBackupManager = () => {
    setShowBackupManager(false);
  };

  const handleBackupSuccess = (result) => {
    setToast({
      isOpen: true,
      message: `Successfully re-applied ${result.total_processed} backup(s).`,
      variant: 'success'
    });
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

  const needsNormalization = normalizationStatus?.needs_normalization || false;
  const isNormalizationRunning = normalizationStatus?.is_running || false;

  return (
    <>
      <ConfirmDialog
        isOpen={showNormalizeConfirm}
        title="Normalize All Districts"
        message="This will normalize salary data across all districts. This may take several minutes. Continue?"
        confirmText="Start Normalization"
        cancelText="Cancel"
        variant="default"
        onConfirm={confirmNormalize}
        onCancel={() => setShowNormalizeConfirm(false)}
      />

      <Toast
        isOpen={toast.isOpen}
        message={toast.message}
        variant={toast.variant}
        onClose={() => setToast({ ...toast, isOpen: false })}
      />

      <div className="user-menu">
        <button className="user-icon-button logged-in" onClick={toggleMenu} title={user.email}>
          <svg className="user-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="10" r="3" />
            <path d="M6.168 18.849A4 4 0 0 1 10 16h4a4 4 0 0 1 3.834 2.855" />
          </svg>
          {user.is_admin && <span className="admin-dot"></span>}
          {needsNormalization && <span className="normalization-badge" title="Normalization needed"></span>}
        </button>

      {showMenu && (
        <div className="user-dropdown">
          <div className="user-info">
            <div className="user-info-email">{user.email}</div>
            {user.is_admin && <span className="user-info-badge">Administrator</span>}
          </div>
          <hr />
          {user.is_admin && (
            <>
              <button
                className="menu-button normalize-button"
                onClick={handleNormalize}
                disabled={!needsNormalization || isNormalizing || isNormalizationRunning}
              >
                <svg className="menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                {isNormalizationRunning
                  ? 'Normalizing...'
                  : isNormalizing
                  ? 'Starting...'
                  : 'Normalize All Districts'}
                {needsNormalization && <span className="badge-dot"></span>}
              </button>
              <button
                className="menu-button backup-button"
                onClick={handleOpenBackupManager}
              >
                <svg className="menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <path d="M12 18v-6" />
                  <path d="m9 15 3 3 3-3" />
                </svg>
                Backup Manager
              </button>
              <hr />
            </>
          )}
          <button className="menu-button logout-button" onClick={handleLogout}>
            <svg className="logout-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Logout
          </button>
        </div>
      )}

      {/* Backup Manager Modal */}
      {showBackupManager && (
        <BackupManager
          onClose={handleCloseBackupManager}
          onSuccess={handleBackupSuccess}
        />
      )}
    </div>
    </>
  );
}

export default Login;