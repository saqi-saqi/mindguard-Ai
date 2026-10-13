import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import DocScreenshots from './DocScreenshots.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import './index.css'

const params = new URLSearchParams(window.location.search);
const isScreenMode = params.has('screen');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      {isScreenMode ? <DocScreenshots /> : <App />}
    </ErrorBoundary>
  </React.StrictMode>,
)
