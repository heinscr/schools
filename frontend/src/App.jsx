import { useState } from 'react'
import DistrictBrowser from './components/DistrictBrowser'
import Login from './components/Login'
import { DataCacheProvider } from './contexts/DataCacheContext'
import ErrorBoundary from './components/ErrorBoundary'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [isAuthLoading, setIsAuthLoading] = useState(false)

  const handleAuthChange = (userData) => {
    setUser(userData)
  }

  const handleAuthLoadingChange = (loading) => {
    setIsAuthLoading(loading)
  }

  return (
    <ErrorBoundary
      errorTitle="Application Error"
      errorMessage="The application encountered an unexpected error. Please refresh the page."
      showDetails={false}
    >
      <DataCacheProvider autoLoad={true}>
        <div className="app">
          <div className="app-header-auth">
            <ErrorBoundary
              errorTitle="Authentication Error"
              errorMessage="There was a problem with authentication. Please try logging in again."
              showDetails={false}
            >
              <Login
                onAuthChange={handleAuthChange}
                onLoadingChange={handleAuthLoadingChange}
              />
            </ErrorBoundary>
          </div>
          <ErrorBoundary
            errorTitle="District Browser Error"
            errorMessage="There was a problem loading the district browser. Please refresh the page."
            showDetails={false}
          >
            <DistrictBrowser user={user} />
          </ErrorBoundary>
          {isAuthLoading && (
            <div className="auth-backdrop">
              <div className="auth-modal">
                <div className="auth-spinner"></div>
                <p>Authenticating...</p>
              </div>
            </div>
          )}
        </div>
      </DataCacheProvider>
    </ErrorBoundary>
  )
}

export default App