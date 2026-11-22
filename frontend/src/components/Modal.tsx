// A window over the page (native <dialog>, modal where the browser has it): it opens next to what
// the person clicked instead of far down the page, keeps the focus inside, and Esc closes it.
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";

import { Icon } from "./Icon";

/** Opens the dialog as a modal once it is on the page; `close()` gives the focus back. */
export function useModal(ref: RefObject<HTMLDialogElement | null>) {
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }, [ref]);
  return () => {
    if (typeof ref.current?.close === "function") ref.current.close();
  };
}

export function Modal({
  title,
  onClose,
  wide = false,
  size,
  children,
}: {
  title: ReactNode;
  onClose: () => void;
  /** For a large view (a participant's details) rather than a short form; the same as
   * size="wide". */
  wide?: boolean;
  /** "medium" for a small table (a participant's documents), "wide" for a large view; a short
   * form when not given. */
  size?: "medium" | "wide";
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const closeModal = useModal(ref);
  const close = () => {
    closeModal();
    onClose();
  };
  const width = size ?? (wide ? "wide" : null);
  return (
    <dialog
      ref={ref}
      className={width ? `dialog dialog--${width}` : "dialog"}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="dialog__head">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="dialog__close" onClick={close}>
          <Icon name="close" size={18} />
          <span className="sr-only">Close</span>
        </button>
      </div>
      <div className="dialog__body">{children}</div>
    </dialog>
  );
}
