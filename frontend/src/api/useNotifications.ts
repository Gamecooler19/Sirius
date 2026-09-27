/** Real Web Push opt-in control (Module 20) -- wraps the browser's own
 * `PushManager` API (`pushManager.subscribe()`/`.getSubscription()`/
 * `.unsubscribe()`) plus the backend's
 * `POST`/`DELETE /notifications/subscribe` endpoints.
 *
 * **Never auto-prompts.** Every function this hook exposes is a plain
 * async function invoked from a real click handler
 * (`ProfilePage`'s own "Enable notifications" button) -- nothing here
 * runs on mount, on login, or on any effect with no direct user
 * action as its cause. `Notification.requestPermission()` (invoked
 * transitively by `pushManager.subscribe()`) only ever shows the
 * browser's own permission prompt in response to a genuine user
 * gesture; calling it from a `useEffect` would be exactly the
 * "unrequested browser permission prompt" this module's own
 * requirement explicitly rules out, and most browsers auto-deny or
 * auto-block a permission request that did not originate from a
 * user gesture anyway -- so an auto-prompt would likely not even work,
 * on top of being bad practice.
 */

import { useCallback, useEffect, useState } from "react";
import { api } from "./client";
import type { PushSubscribeRequest, VapidPublicKeyResponse } from "./types";

/** Converts the VAPID public key's own base64url string (the wire
 * format `GET /notifications/vapid-public-key` returns, and the exact
 * format `py_vapid`/`pywebpush` produce) into the raw `Uint8Array` the
 * browser's own `pushManager.subscribe({ applicationServerKey })`
 * requires -- the browser API takes a `BufferSource`, not a string, so
 * this conversion is unavoidable regardless of implementation.
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export type NotificationSupportState = "unsupported" | "unsubscribed" | "subscribed";

/** Reports whether *this browser* currently has an active push
 * subscription -- read directly from the real `PushManager`
 * (`getSubscription()`), never from a client-side flag the app itself
 * set, so a subscription cleared by the OS/browser (or by this
 * server's own dead-subscription cleanup, see `app.core.push`'s own
 * docstring) is reflected correctly on the next load rather than a
 * stale "subscribed" state the UI has no way to know is now wrong.
 */
export function useNotificationSubscription() {
  const [state, setState] = useState<NotificationSupportState>("unsubscribed");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshState = useCallback(async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const existing = await registration.pushManager.getSubscription();
    setState(existing ? "subscribed" : "unsubscribed");
  }, []);

  useEffect(() => {
    // Reading current state on mount is not itself a permission
    // request -- getSubscription() never prompts, it only reports
    // whether a subscription this browser already established (via a
    // real prior click on the button below) still exists.
    void refreshState();
  }, [refreshState]);

  const subscribe = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const registration = await navigator.serviceWorker.ready;
      const { public_key } = await api.get<VapidPublicKeyResponse>(
        "/notifications/vapid-public-key",
      );

      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });

      const json = subscription.toJSON();
      await api.post<void>("/notifications/subscribe", {
        endpoint: json.endpoint,
        keys: { p256dh: json.keys!.p256dh, auth: json.keys!.auth },
      } satisfies PushSubscribeRequest);

      setState("subscribed");
    } catch (e) {
      // The browser itself throws a real, specific error (e.g.
      // "Registration failed - permission denied") when the user
      // dismisses or blocks the permission prompt -- surfaced verbatim
      // rather than a rewritten generic message, the same "show the
      // real rejection reason" discipline this codebase's own backend
      // error handling already follows.
      setError(e instanceof Error ? e.message : "failed to enable notifications");
    } finally {
      setBusy(false);
    }
  }, []);

  const unsubscribe = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();
      if (existing) {
        const endpoint = existing.endpoint;
        await existing.unsubscribe();
        await api.delete<void>("/notifications/subscribe", { endpoint });
      }
      setState("unsubscribed");
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to disable notifications");
    } finally {
      setBusy(false);
    }
  }, []);

  return { state, error, busy, subscribe, unsubscribe };
}
