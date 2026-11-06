import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import './styles/tokens.css'
import './styles/globals.css'
import { Providers } from './app/providers'
import { router } from './app/router'
import { isMock } from './config/env'

// Read ?mock=1 once at startup so the choice survives navigation, even on pages that make no API call (the landing page).
isMock()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
)
