// Requirements: FND-018
// Codes in words, dates in Indian English and India time, browsers by name (UI review 2026-11-17).
import { describe, expect, it } from "vitest";

import { clock, day, duration, when } from "./format";
import {
  CONSENT_METHOD_LABELS,
  consentAnswer,
  consentCounts,
  labelFor,
  PRIORITY_LABELS,
  REASON_LABELS,
  reasonChoices,
  TASK_STATUS_LABELS,
} from "./labels";
import { describeUserAgent } from "./userAgent";

describe("labels", () => {
  it("gives every code words, and a readable fallback for a new one", () => {
    expect(labelFor(PRIORITY_LABELS, "NORMAL")).toBe("Normal");
    expect(labelFor(REASON_LABELS, "AUDIO_QUALITY")).toBe("Poor audio quality");
    expect(labelFor(CONSENT_METHOD_LABELS, "VERBAL_RECORDED")).toBe("Said yes on the recording");
    expect(labelFor({}, "SOME_NEW_CODE")).toBe("Some new code");
    expect(labelFor({}, null)).toBe("-");
  });

  it("names every task status, a consent form to fix too (D-146)", () => {
    expect(labelFor(TASK_STATUS_LABELS, "CONSENT_FIX")).toBe("Consent form to fix");
    // The task list's filter offers them in the order of the work: the fix right after Audio QC.
    const order = Object.keys(TASK_STATUS_LABELS);
    expect(order.indexOf("CONSENT_FIX")).toBe(order.indexOf("AUDIO_QC") + 1);
    expect(order).toHaveLength(11);
  });

  it("says the consent answer and its colour", () => {
    expect(consentAnswer("GIVEN")).toEqual({ label: "Agreed", tone: "success" });
    expect(consentAnswer(null)).toEqual({ label: "No answer yet", tone: "neutral" });
  });

  it("says a signed form was uploaded, or is missing where the project takes them (D-144)", () => {
    expect(consentAnswer("UPLOADED")).toEqual({ label: "Form uploaded", tone: "success" });
    expect(consentAnswer("NONE", "UPLOAD")).toEqual({
      label: "Consent form missing",
      tone: "warning",
    });
    expect(consentAnswer(null, "UPLOAD").label).toBe("Consent form missing");
    expect(consentAnswer("GIVEN", "UPLOAD").label).toBe("Agreed");
    expect(consentAnswer("NONE", "ONLINE").label).toBe("No answer yet");
    expect(["GIVEN", "UPLOADED", "REFUSED", "NONE", null].map(consentCounts)).toEqual([
      true,
      true,
      false,
      false,
      false,
    ]);
  });

  it("turns the server's reason codes into a choice list", () => {
    expect(reasonChoices(["WAITING_FOR_PARTICIPANT", "OTHER"])).toEqual({
      WAITING_FOR_PARTICIPANT: "Waiting for a participant",
      OTHER: "Other (explain in the comment)",
    });
    expect(reasonChoices(undefined)).toEqual({});
  });
});

describe("dates and lengths", () => {
  it("shows times in India time, whatever the computer's own zone", () => {
    // 08:27 UTC is 1:57 pm in India.
    expect(when("2026-11-17T08:27:00Z")).toMatch(/^17 Nov 2026, 1:57\s?pm$/);
    expect(day("2026-11-17T20:00:00Z")).toBe("18 Nov 2026");
    expect(when(null)).toBe("-");
  });

  it("shows lengths in seconds, minutes or hours", () => {
    expect(duration(42)).toBe("42 s");
    expect(duration(720)).toBe("12.0 min");
    expect(clock(247)).toBe("4:07");
  });
});

describe("browsers", () => {
  it("names the browser and the system instead of the raw text", () => {
    const edge =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " +
      "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0";
    const iphone =
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like " +
      "Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
    expect(describeUserAgent(edge)).toBe("Edge on Windows");
    expect(describeUserAgent(iphone)).toBe("Safari on iPhone or iPad");
    expect(describeUserAgent(null)).toBe("Unknown browser");
  });
});
