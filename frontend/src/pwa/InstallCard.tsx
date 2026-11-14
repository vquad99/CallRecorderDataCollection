// "Install the application" on the My account page (PWA-002, PWA-009, D-110): the browser's own
// install offer when it made one, and otherwise how to do it in each browser.
import { useState, useSyncExternalStore } from "react";

import { Button } from "../components/form/Button";
import { SuccessNotice } from "../components/Notice";
import { installOffer, isInstalled, onInstallOffer, clearInstallOffer } from "./install";

export function InstallCard() {
  const offer = useSyncExternalStore(onInstallOffer, installOffer);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (isInstalled()) {
    return (
      <section className="card" aria-labelledby="install-title">
        <h2 id="install-title">Installed application</h2>
        <p>You are using the installed application. It still needs a connection to work.</p>
      </section>
    );
  }
  return (
    <section className="card stack stack--tight" aria-labelledby="install-title">
      <h2 id="install-title">Install the application</h2>
      <p>
        Installed, it opens in its own window from your desktop or home screen, like any other
        application. It still needs a connection: nothing is kept on this device.
      </p>
      {offer ? (
        <div className="actions">
          <Button
            busy={busy}
            onClick={() => {
              setBusy(true);
              void offer
                .prompt()
                .then(() => offer.userChoice)
                .then((choice) => {
                  setMessage(
                    choice.outcome === "accepted"
                      ? "Installed. Look for Conversation Collection among your applications."
                      : "Not installed. You can install it later from the browser's menu.",
                  );
                  clearInstallOffer();
                })
                .catch(() => setMessage("The browser did not open its install window."))
                .finally(() => setBusy(false));
            }}
          >
            Install
          </Button>
        </div>
      ) : (
        <>
          <p>Your browser has not offered to install it on this page. You can do it yourself:</p>
          <ul className="list">
            <li>
              <strong>Chrome or Edge on a computer:</strong> the install icon at the right end of
              the address bar, or the browser&apos;s menu, then &quot;Install Conversation
              Collection&quot; (Edge: Apps, then &quot;Install this site as an app&quot;).
            </li>
            <li>
              <strong>Chrome on an Android phone:</strong> the menu (three dots), then &quot;Add to
              Home screen&quot; or &quot;Install app&quot;.
            </li>
            <li>
              <strong>Safari on an iPhone or iPad:</strong> the Share button, then &quot;Add to Home
              Screen&quot;.
            </li>
            <li>
              <strong>Firefox on a computer</strong> cannot install applications: use Chrome or
              Edge.
            </li>
          </ul>
        </>
      )}
      <SuccessNotice message={message} />
    </section>
  );
}
