// Requirements: FND-019
// The one confirmation window (UI review 2026-11-17): it can ask why, keeps what was typed when
// the action fails, and closes only when the action has worked.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { useConfirm, type ConfirmOptions } from "./ConfirmDialog";

function Page({
  options,
  onMessage,
}: {
  options: ConfirmOptions;
  onMessage?: (m: string) => void;
}) {
  const confirm = useConfirm(onMessage);
  return (
    <>
      <button type="button" onClick={() => confirm.ask(options)}>
        Open
      </button>
      {confirm.dialog}
    </>
  );
}

describe("confirmation window", () => {
  it("asks for a reason from the list, and a comment when the reason is Other", async () => {
    const action = vi.fn(() => Promise.resolve("Task cancelled."));
    const onMessage = vi.fn();
    render(
      <Page
        onMessage={onMessage}
        options={{
          title: "Cancel task T000001?",
          confirmLabel: "Cancel task",
          danger: true,
          reasons: { CLIENT_REQUEST: "The client asked", OTHER: "Other (explain in the comment)" },
          action,
        }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    const box = within(screen.getByRole("dialog", { name: "Cancel task T000001?" }));
    const confirm = box.getByRole("button", { name: "Cancel task" });
    expect(confirm).toHaveClass("button--danger");
    expect(confirm).toBeDisabled();
    await userEvent.selectOptions(box.getByLabelText(/^Reason/), "OTHER");
    expect(confirm).toBeDisabled();
    await userEvent.type(box.getByLabelText(/^Comment/), "Duplicate of T000002");
    await userEvent.click(confirm);
    expect(action).toHaveBeenCalledWith({ reason: "OTHER", comment: "Duplicate of T000002" });
    expect(onMessage).toHaveBeenCalledWith("Task cancelled.");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the window and what was typed when the action fails, and says why", async () => {
    const action = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError({ status: 409, code: "TASK_HAS_WORK", message: "Cancel it instead." }),
      )
      .mockResolvedValueOnce(undefined);
    render(
      <Page
        options={{
          title: "Delete task?",
          askReason: "Why is it deleted?",
          confirmLabel: "Delete task",
          action,
        }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    const box = within(screen.getByRole("dialog"));
    await userEvent.type(box.getByLabelText(/Why is it deleted/), "Made twice");
    await userEvent.click(box.getByRole("button", { name: "Delete task" }));
    expect(await box.findByRole("alert")).toHaveTextContent("Cancel it instead.");
    expect(box.getByLabelText(/Why is it deleted/)).toHaveValue("Made twice");
    await userEvent.click(box.getByRole("button", { name: "Delete task" }));
    expect(action).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does nothing when the person goes back", async () => {
    const action = vi.fn(() => Promise.resolve());
    render(<Page options={{ title: "Remove?", confirmLabel: "Remove", action }} />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await userEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(action).not.toHaveBeenCalled();
  });
});
