import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@mantine/core/styles.css'
import './index.css'
import App from './App.tsx'

// Module 20: registers the real service worker (public/sw.js) at app
// startup -- registration alone, never a push subscription attached
// here. A registered-but-unsubscribed service worker is inert (no
// permission prompt, no observable behavior change); the actual
// `pushManager.subscribe()` call that can trigger a real browser
// permission prompt only ever runs from ProfilePage's own explicit
// opt-in button (`useNotificationSubscription`), never automatically
// on login -- see that hook's own docstring for the full reasoning.
// `serviceWorker in navigator` guards browsers/contexts (e.g. very old
// browsers, some embedded webviews) that lack the API entirely, so
// registration failing there is a silent no-op, not a thrown error
// that would break the rest of the app's own startup.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch((err) => {
    console.error('service worker registration failed', err)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
