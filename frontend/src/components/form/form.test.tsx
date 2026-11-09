// Requirements: FND-019
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";
import { TextField } from "./TextField";

describe("form controls", () => {
  it("links label, hint and error to the input", () => {
    render(<TextField label="Email" hint="Work address" error="Required" required />);
    const input = screen.getByLabelText(/Email/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Work address Required");
    expect(input).toBeRequired();
  });

  it("button defaults to type=button and announces busy", () => {
    render(<Button busy>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
  });

  it("has no axe accessibility violations", async () => {
    const { container } = render(
      <form aria-label="Example">
        <TextField label="Name" hint="As written on ID" />
        <TextField label="Phone" error="Invalid number" />
        <Button type="submit">Submit</Button>
      </form>,
    );
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});
