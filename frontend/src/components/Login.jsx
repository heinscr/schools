import { useState, useEffect } from 'react';
import authService from '../services/auth';
import './Login.css';

function Login({ onAuthChange }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showMenu, setShowMenu] = useState(false);

  useEffect(() => {
    initAuth();
  }, []);

  const initAuth = async () => {
    try {
      // Initialize auth service
      await authService.init();

      // Check for OAuth callback
      const hasCallback = authService.handleCallback();

      if (hasCallback) {
        // If we just completed authentication, fetch user details
        await fetchUserDetails();
      } else if (authService.isAuthenticated()) {
        // If already authenticated, fetch user details
        await fetchUserDetails();
      } else {
        setLoading(false);
      }
    } catch (error) {
      console.error('Auth initialization error:', error);
      setLoading(false);
    }
  };

  const fetchUserDetails = async () => {
    try {
      const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const authData = await authService.getCurrentUser(apiBaseUrl);

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
    authService.login();
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

  if (loading) {
    return null; // Don't show anything while loading
  }

  if (!user) {
    return (
      <button className="login-button" onClick={handleLogin}>
        <span className="login-icon">👤</span>
        <span className="login-text">Login</span>
      </button>
    );
  }

  return (
    <div className="user-menu">
      <button className="user-button" onClick={toggleMenu}>
        <span className="user-icon">👤</span>
        <span className="user-email">{user.email}</span>
        {user.is_admin && <span className="admin-badge">Admin</span>}
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
