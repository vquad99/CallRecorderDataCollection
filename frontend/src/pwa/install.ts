// The browser's offer to install the application (PWA-002, D-110). The offer can come before
// any page asks about it, so it is caught as soon as the application starts and kept until a
// page (My account) uses it.

/** The part of the browser's `beforeinstallprompt` event that is used here. */
export interface InstallOffer {
  prompt: () => Promise<unknown>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let offer: InstallOffer | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

export function watchInstallOffer(): void {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // the application shows its own button instead of the browser's bar
    offer = event as unknown as InstallOffer;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    offer = null;
    changed();
  });
}

export const installOffer = (): InstallOffer | null => offer;

export function onInstallOffer(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Forget the offer once it has been used: a browser lets it be shown once. */
export function clearInstallOffer(): void {
  offer = null;
  changed();
}

/** Whether this window is the installed application, not a browser tab. */
export function isInstalled(): boolean {
  const standalone =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(display-mode: standalone)").matches;
  return standalone || (navigator as { standalone?: boolean }).standalone === true;
}
