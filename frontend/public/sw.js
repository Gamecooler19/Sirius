/**
 * Sirius service worker (Module 20): extends Module 13's PWA manifest
 * work (`public/site.webmanifest`, the icon set) with the two real Web
 * Push event handlers a manifest alone cannot provide -- `push` (a
 * message actually arrived, show it) and `notificationclick` (the user
 * tapped it, focus or open the app at the relevant route). No caching,
 * no offline strategy, no fetch interception of any kind -- this
 * service worker exists solely to receive push messages while no tab is
 * necessarily focused; broadening its scope into a general offline/
 * cache worker is explicitly out of this module's scope and would risk
 * silently changing how the app's own API/asset requests behave for a
 * feature that was never asked for.
 *
 * Registered from `frontend/src/main.tsx` at the app's own root scope
 * (`/`) -- not auto-registered on every page load unconditionally with
 * a push subscription attached; registration and subscription are two
 * separate steps, and only registration happens automatically (a
 * service worker with no active subscription is inert and does nothing
 * observable). The actual `pushManager.subscribe()` call -- the one
 * that can trigger a real, user-visible permission prompt -- only ever
 * runs from `ProfilePage`'s own explicit opt-in button, per this
 * module's own explicit requirement: "never auto-prompt for
 * notification permission on login."
 */

self.addEventListener("push", (event) => {
  let payload = { title: "Sirius", body: "You have a new notification.", url: "/" };
  if (event.data) {
    try {
      payload = event.data.json();
    } catch {
      // A push service is free to deliver a non-JSON payload in
      // principle; this server never sends one (app.core.push always
      // JSON-encodes), but falling back to the generic payload above
      // rather than throwing keeps a malformed message from silently
      // dropping the notification entirely.
      payload.body = event.data.text();
    }
  }

  const options = {
    body: payload.body,
    icon: "/icon-192.png",
    badge: "/favicon-32x32.png",
    // The in-app route notificationclick below navigates to -- carried
    // through Notification.data rather than re-parsed from the
    // notification's own title/body text, so the click handler needs
    // no string parsing to recover it.
    data: { url: payload.url || "/" },
  };

  event.waitUntil(self.registration.showNotification(payload.title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = new URL(event.notification.data?.url || "/", self.location.origin).href;

  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      // Prefer focusing an already-open Sirius tab over opening a new
      // one -- a real multi-tab user should not accumulate a fresh tab
      // per notification click. `navigate()` (not merely `focus()`)
      // moves that existing tab to the relevant route even if it was
      // sitting on an unrelated page.
      for (const client of allClients) {
        if ("focus" in client) {
          await client.navigate(targetUrl);
          return client.focus();
        }
      }

      return self.clients.openWindow(targetUrl);
    })(),
  );
});
