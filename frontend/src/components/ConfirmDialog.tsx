// The one confirmation for actions that change or remove something (a native <dialog>). It can
// ask why: in words ("Why is it deleted?"), or as a reason from a fixed list with a comment that
// "Other" needs. It runs the action itself and stays open, with what was typed and any error,
// until the action has worked. Use it through useConfirm():
//   const confirm = useConfirm(setMessage);
//   confirm.ask({ title: "Delete task?", confirmLabel: "Delete task", danger: true,
//                 action: async () => { await deleteTask(id); return "Task deleted."; } });
//   ...and render {confirm.dialog} once in the component.
import { useId, useRef, useState, type ReactNode } from "react";

import { useAction } from "../hooks/useAction";
import { Button } from "./form/Button";
import { Select } from "./form/Select";
import { TextField } from "./form/TextField";
import { useModal } from "./Modal";
import { ErrorNotice } from "./Notice";

export interface ConfirmAnswer {
  /** The chosen reason code; "" when no list was offered. */
  reason: string;
  /** The words typed; "" when none. */
  comment: string;
}

export interface ConfirmOptions {
  title: string;
  message?: ReactNode;
  confirmLabel: string;
  /** A red confirm button: the action deletes, rejects or ends something. */
  danger?: boolean;
  /** Ask for a reason in words; the confirm button waits until one is typed. */
  askReason?: string;
  /** Ask for a reason from a fixed list (code: words). "OTHER" also needs a comment. */
  reasons?: Record<string, string>;
  /** The comment's label with a reason list ("Comment" when not given). */
  commentLabel?: string;
  /** What happens on confirm. A string it returns is the message for the page. */
  action: (answer: ConfirmAnswer) => Promise<unknown>;
}

/** A reason from a fixed list and a comment, which "Other" makes required. */
export function ReasonFields({
  reasons,
  reason,
  comment,
  onReason,
  onComment,
  commentLabel = "Comment",
}: {
  reasons: Record<string, string>;
  reason: string;
  comment: string;
  onReason: (code: string) => void;
  onComment: (text: string) => void;
  commentLabel?: string;
}) {
  const needed = reason === "OTHER";
  return (
    <>
      <Select
        label="Reason"
        required
        value={reason}
        onChange={(e) => onReason(e.target.value)}
        options={[
          { value: "", label: "Choose a reason" },
          ...Object.entries(reasons).map(([value, label]) => ({ value, label })),
        ]}
      />
      <TextField
        label={commentLabel}
        required={needed}
        {...(needed ? {} : { hint: "Optional. Needed when the reason is Other." })}
        value={comment}
        onChange={(e) => onComment(e.target.value)}
      />
    </>
  );
}

function ConfirmDialog({
  options,
  onClose,
  onMessage,
}: {
  options: ConfirmOptions;
  onClose: () => void;
  onMessage: ((message: string) => void) | undefined;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const { busy, error, run } = useAction();
  const closeModal = useModal(ref);
  const close = () => {
    closeModal();
    onClose();
  };
  const needsComment = Boolean(options.askReason) || reason === "OTHER";
  const ready = (!options.reasons || reason !== "") && (!needsComment || comment.trim() !== "");
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        if (busy === null) close();
      }}
    >
      <form
        className="dialog__body"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ready || busy !== null) return;
          void run(async () => {
            const result = await options.action({ reason, comment: comment.trim() });
            if (typeof result === "string") onMessage?.(result);
            close();
          });
        }}
      >
        <h2 id={titleId}>{options.title}</h2>
        {options.message ? <div className="dialog__message">{options.message}</div> : null}
        {options.reasons ? (
          <ReasonFields
            reasons={options.reasons}
            reason={reason}
            comment={comment}
            onReason={setReason}
            onComment={setComment}
            {...(options.commentLabel ? { commentLabel: options.commentLabel } : {})}
          />
        ) : null}
        {options.askReason ? (
          <TextField
            label={options.askReason}
            required
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        ) : null}
        <ErrorNotice error={error} />
        <div className="dialog__actions">
          <Button variant="secondary" disabled={busy !== null} onClick={close}>
            Go back
          </Button>
          <Button
            type="submit"
            variant={options.danger ? "danger" : "primary"}
            busy={busy !== null}
            disabled={!ready}
          >
            {options.confirmLabel}
          </Button>
        </div>
      </form>
    </dialog>
  );
}

/** `ask(options)` opens the confirmation; render `dialog` once in the component that asks.
 * `onMessage` receives the message an action returns ("Task deleted."). */
export function useConfirm(onMessage?: (message: string) => void) {
  const [asked, setAsked] = useState<ConfirmOptions | null>(null);
  const dialog = asked ? (
    <ConfirmDialog options={asked} onClose={() => setAsked(null)} onMessage={onMessage} />
  ) : null;
  return { ask: setAsked as (options: ConfirmOptions) => void, dialog };
}
