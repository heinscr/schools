import { useState } from 'react'
import DistrictBrowser from './components/DistrictBrowser'
import Login from './components/Login'
import { DataCacheProvider } from './contexts/DataCacheContext'
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
    <DataCacheProvider autoLoad={true}>
      <div className="app">
        <div className="app-header-auth">
          <Login
            onAuthChange={handleAuthChange}
            onLoadingChange={handleAuthLoadingChange}
          />
        </div>
        <DistrictBrowser user={user} />
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
  )
}

export default App
