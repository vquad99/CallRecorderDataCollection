// The fixed lists behind the dropdowns (D-083): language names, and phone numbers by country.
// Requirements: PART-004, PART-005, PROJ-002
import { describe, expect, it } from "vitest";

import {
  COUNTRY_CODES,
  LANGUAGES,
  languageLabel,
  languageOptions,
  OTHER_CODE,
  phoneDigits,
  phoneProblem,
  splitPhone,
} from "./choices";

describe("languages", () => {
  it("lists all 22 languages of India's Eighth Schedule, each code once", () => {
    const scheduled = ["as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml"];
    scheduled.push("mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur");
    const codes = LANGUAGES.map((l) => l.code);
    expect(scheduled.filter((code) => !codes.includes(code))).toEqual([]);
    expect(new Set(codes).size).toBe(codes.length);
    for (const code of ["en-US", "en-GB", "es-MX", "pt-BR", "fr-CA", "zh-TW"]) {
      expect(codes).toContain(code);
    }
  });

  it("names a listed code by the list, another by the browser's name, and shows the rest as they are", () => {
    expect(languageLabel("kok")).toBe("Konkani (kok)");
    expect(languageLabel("sat")).toBe("Santali (sat)");
    expect(languageLabel("pt-BR")).toBe("Portuguese (Brazil) (pt-BR)");
    const swahili = new Intl.DisplayNames(["en"], { type: "language" }).of("sw");
    expect(languageLabel("sw")).toBe(swahili && swahili !== "sw" ? `${swahili} (sw)` : "sw");
    // Not a well-formed code: the browser refuses it, the page still shows it.
    expect(languageLabel("Hindi!")).toBe("Hindi!");
    expect(languageLabel("")).toBe("");
  });

  it("offers the project's own languages, and the whole list when it has none", () => {
    const own = languageOptions([
      { language_code: "kok", dialect: "Goan" },
      { language_code: "kok", dialect: "Mangalorean" },
    ]);
    expect(own.map((o) => o.value)).toEqual(["", "kok"]);
    expect(languageOptions([]).length).toBe(LANGUAGES.length + 1);
  });
});

describe("phone numbers", () => {
  it("takes exactly 10 digits after +91, and what the server takes after any other code", () => {
    expect(phoneDigits("+91")).toEqual({ min: 10, max: 10 });
    // E.164: 8 to 15 digits in all, the country code included.
    expect(phoneDigits("+1")).toEqual({ min: 7, max: 14 });
    expect(phoneDigits("+65")).toEqual({ min: 6, max: 13 });
    expect(phoneDigits("+971")).toEqual({ min: 5, max: 12 });
    expect(phoneDigits(OTHER_CODE)).toEqual({ min: 8, max: 15 });
  });

  it("says what is wrong in the country's own terms", () => {
    expect(phoneProblem("+91", "")).toBe("");
    expect(phoneProblem("+91", "9876543210")).toBe("");
    expect(phoneProblem("+91", "09876543210")).toBe("Type exactly 10 digits (you typed 11).");
    expect(phoneProblem("+65", "91234567")).toBe("");
    expect(phoneProblem("+65", "9123")).toBe("Type 6 to 13 digits (you typed 4).");
    expect(phoneProblem("+86", "13812345678")).toBe("");
    expect(phoneProblem(OTHER_CODE, "48601234567")).toBe("");
    expect(phoneProblem(OTHER_CODE, "0048601234567")).toBe(
      "Start with the country code, without 00 or +.",
    );
  });

  it("splits a stored number by the longest listed code, and keeps an unlisted one whole", () => {
    expect(splitPhone("+919876543210")).toEqual({ cc: "+91", digits: "9876543210" });
    expect(splitPhone("+97150123456")).toEqual({ cc: "+971", digits: "50123456" });
    expect(splitPhone("+8801712345678")).toEqual({ cc: "+880", digits: "1712345678" });
    expect(splitPhone("+48601234567")).toEqual({ cc: OTHER_CODE, digits: "48601234567" });
    expect(splitPhone("+41 79 123 45 67")).toEqual({ cc: OTHER_CODE, digits: "41791234567" });
    expect(splitPhone("")).toEqual({ cc: "+91", digits: "" });
    expect(splitPhone(null)).toEqual({ cc: "+91", digits: "" });
    // Put back together, a number is what was stored.
    for (const stored of ["+919876543210", "+6591234567", "+48601234567", "+12025550123"]) {
      const { cc, digits } = splitPhone(stored);
      expect(`${cc}${digits}`).toBe(stored);
    }
    expect(COUNTRY_CODES.at(-1)).toEqual({
      code: OTHER_CODE,
      name: "Other (type the country code too)",
    });
  });
});
