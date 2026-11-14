// Starts the service worker and tells the person when a new version is ready (PWA-005, D-110).
// Loaded after the first screen, in the built application only.
import "./pwa.css";

const CHECK_MS = 30 * 60 * 1000; // look for a new version this often while the page stays open

/** The bar that offers the new version. Nothing reloads by itself: a recording may be running. */
function showUpdate(onReload: () => void): void {
  if (document.getElementById("pwa-update")) return;
  const bar = document.createElement("div");
  bar.id = "pwa-update";
  bar.className = "pwa-update";
  bar.setAttribute("role", "status");
  const text = document.createElement("span");
  text.textContent =
    "A new version of the application is ready. Reload when you are not in the middle of a recording.";
  const reload = document.createElement("button");
  reload.type = "button";
  reload.className = "button button--primary";
  reload.textContent = "Reload";
  reload.addEventListener("click", () => {
    reload.disabled = true;
    onReload();
  });
  const later = document.createElement("button");
  later.type = "button";
  later.className = "button button--secondary";
  later.textContent = "Later";
  later.addEventListener("click", () => bar.remove());
  bar.append(text, reload, later);
  document.body.append(bar);
}

export function registerServiceWorker(
  container: ServiceWorkerContainer = navigator.serviceWorker,
  reload: () => void = () => window.location.reload(),
): void {
  let asked = false;
  // The page reloads only after the person asked for the new version: the first time a worker
  // takes the page over (a first visit) nothing must reload.
  container.addEventListener("controllerchange", () => {
    if (asked) reload();
  });
  container
    .register("/sw.js")
    .then((registration) => {
      const offer = (worker: ServiceWorker | null) => {
        if (!worker) return;
        const whenReady = () => {
          // "installed" with a worker already in charge means: a newer one is waiting.
          if (worker.state === "installed" && container.controller) {
            showUpdate(() => {
              asked = true;
              worker.postMessage("skip-waiting");
            });
          }
        };
        whenReady();
        worker.addEventListener("statechange", whenReady);
      };
      offer(registration.waiting);
      registration.addEventListener("updatefound", () => offer(registration.installing));
      const look = () => {
        registration.update().catch(() => undefined); // offline: the next look will do
      };
      window.setInterval(look, CHECK_MS);
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") look();
      });
    })
    .catch((error: unknown) => {
      console.error("The service worker could not be started", error);
    });
}
