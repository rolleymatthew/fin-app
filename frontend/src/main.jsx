import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import Etf from './Etf.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Etf />
  </StrictMode>,
)
