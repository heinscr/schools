import { useState } from 'react'
import DistrictBrowser from './components/DistrictBrowser'
import Login from './components/Login'
import './App.css'

function App() {
  const [user, setUser] = useState(null)

  const handleAuthChange = (userData) => {
    setUser(userData)
  }

  return (
    <div className="app">
      <div className="app-header-auth">
        <Login onAuthChange={handleAuthChange} />
      </div>
      <DistrictBrowser user={user} />
    </div>
  )
}

export default App
