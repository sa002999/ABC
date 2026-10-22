import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './lib/auth'
import { BackendConnection } from './lib/hooks'
import { App } from './App'
import './styles.css'

// Translate legacy hash routes before BrowserRouter reads the URL.
if(window.location.hash.startsWith('#/')){const target=window.location.hash.slice(1);if(!target.startsWith('//')&&!target.includes('\\'))window.history.replaceState(null,'',target)}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><BrowserRouter><BackendConnection><AuthProvider><App /></AuthProvider></BackendConnection></BrowserRouter></React.StrictMode>)
