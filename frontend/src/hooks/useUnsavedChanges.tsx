// A page with changes that are not saved yet asks before they are lost (FEA-04): leaving it for
// another page of the app opens a window ("Leave without saving?", Leave or Stay), and closing or
// reloading the browser tab gets the browser's own question. Use it in the component that holds
// the changes and render what it returns:
//   const leaveGuard = useUnsavedChanges(dirty);
//   ...and {leaveGuard} once in the component.
// Moving within the same page (only the query string or the #part changes) is not leaving, and
// signing out is never held: going to the sign-in page passes. A router holds one guard at a time,
// so only the one component that edits the page uses it.
import { useEffect, useId, useRef } from "react";
import { useBlocker, type BlockerFunction } from "react-router";

import { Button } from "../components/form/Button";
import { useModal } from "../components/Modal";

const SIGN_IN = "/login";

/** The window that asks; Stay keeps the page as it is (Esc too), Leave goes on and drops the
 * changes. */
function LeaveDialog({ onStay, onLeave }: { onStay: () => void; onLeave: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const messageId = useId();
  const closeModal = useModal(ref);
  const answer = (then: () => void) => {
    closeModal();
    then();
  };
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      aria-describedby={messageId}
      onCancel={(e) => {
        e.preventDefault();
        answer(onStay);
      }}
    >
      <div className="dialog__body">
        <h2 id={titleId}>Leave without saving?</h2>
        <p id={messageId} className="dialog__message">
          Your changes on this page are not saved.
        </p>
        <div className="dialog__actions">
          <Button variant="secondary" onClick={() => answer(onStay)}>
            Stay
          </Button>
          <Button variant="danger" onClick={() => answer(onLeave)}>
            Leave
          </Button>
        </div>
      </div>
    </dialog>
  );
}

/** Holds navigation away from a page while `dirty`; returns the window to render. */
export function useUnsavedChanges(dirty: boolean) {
  const shouldBlock: BlockerFunction = ({ currentLocation, nextLocation }) =>
    dirty &&
    currentLocation.pathname !== nextLocation.pathname &&
    nextLocation.pathname !== SIGN_IN;
  const blocker = useBlocker(shouldBlock);

  // Closing the tab, reloading or typing another address: the browser asks in its own words.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Older browsers ask only when a value is set.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  return blocker.state === "blocked" ? (
    <LeaveDialog onStay={() => blocker.reset()} onLeave={() => blocker.proceed()} />
  ) : null;
}

/** The same as a component, for a form that guards only on some pages (it holds nothing where it
 * is not rendered). */
export function UnsavedChangesGuard({ dirty }: { dirty: boolean }) {
  return useUnsavedChanges(dirty);
}
