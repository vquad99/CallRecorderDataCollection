// Fixed lists for the dropdowns: languages and phone country codes (D-083).
import type { Language } from "../../api/projects";

/** Language codes the platform stores (BCP 47: ISO 639, with a region where it matters), with the
 * name people pick from. All 22 languages of India's Eighth Schedule are here. */
export const LANGUAGES: readonly { code: string; name: string }[] = [
  { code: "hi", name: "Hindi" },
  { code: "en", name: "English" },
  { code: "en-IN", name: "English (India)" },
  { code: "en-US", name: "English (United States)" },
  { code: "en-GB", name: "English (United Kingdom)" },
  { code: "bn", name: "Bengali" },
  { code: "ta", name: "Tamil" },
  { code: "te", name: "Telugu" },
  { code: "mr", name: "Marathi" },
  { code: "gu", name: "Gujarati" },
  { code: "kn", name: "Kannada" },
  { code: "ml", name: "Malayalam" },
  { code: "pa", name: "Punjabi" },
  { code: "or", name: "Odia" },
  { code: "as", name: "Assamese" },
  { code: "ur", name: "Urdu" },
  { code: "ne", name: "Nepali" },
  { code: "mai", name: "Maithili" },
  { code: "bho", name: "Bhojpuri" },
  { code: "kok", name: "Konkani" },
  { code: "sd", name: "Sindhi" },
  { code: "ks", name: "Kashmiri" },
  { code: "sa", name: "Sanskrit" },
  { code: "brx", name: "Bodo" },
  { code: "doi", name: "Dogri" },
  { code: "mni", name: "Manipuri" },
  { code: "sat", name: "Santali" },
  { code: "si", name: "Sinhala" },
  { code: "ar", name: "Arabic" },
  { code: "fr", name: "French" },
  { code: "fr-CA", name: "French (Canada)" },
  { code: "de", name: "German" },
  { code: "es", name: "Spanish" },
  { code: "es-MX", name: "Spanish (Mexico)" },
  { code: "pt", name: "Portuguese" },
  { code: "pt-BR", name: "Portuguese (Brazil)" },
  { code: "it", name: "Italian" },
  { code: "ru", name: "Russian" },
  { code: "tr", name: "Turkish" },
  { code: "zh", name: "Chinese" },
  { code: "zh-TW", name: "Chinese (Taiwan)" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "id", name: "Indonesian" },
  { code: "ms", name: "Malay" },
  { code: "th", name: "Thai" },
  { code: "vi", name: "Vietnamese" },
];

/** The browser's own English names for languages, for a code set outside the list (the server
 * takes any well-formed code); null where the browser has none. */
const DISPLAY_NAMES = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "language" });
  } catch {
    return null;
  }
})();

/** "Konkani (kok)"; a code outside the list by the browser's name for it when it has one
 * ("Swahili (sw)"), otherwise the code as it is. */
export const languageLabel = (code: string) => {
  const known = LANGUAGES.find((l) => l.code === code);
  if (known) return `${known.name} (${code})`;
  let name: string | undefined;
  try {
    name = DISPLAY_NAMES?.of(code);
  } catch {
    name = undefined; // not a well-formed code: shown as it is
  }
  return name && name !== code ? `${name} (${code})` : code;
};

/**
 * The choices for a participant's language: the project's own languages when it has any (the
 * server accepts only those), otherwise the whole list. `current` stays choosable when editing.
 */
export function languageOptions(projectLanguages: readonly Language[], current = "") {
  const codes = projectLanguages.length
    ? [...new Set(projectLanguages.map((l) => l.language_code))]
    : LANGUAGES.map((l) => l.code);
  if (current && !codes.includes(current)) codes.push(current);
  return [
    { value: "", label: "Choose a language" },
    ...codes.map((code) => ({ value: code, label: languageLabel(code) })),
  ];
}

/** The "Other" country code: the number box then holds the whole number, its code included. */
export const OTHER_CODE = "+";

/** Phone country codes, India first; "Other" last, for every code not listed. */
export const COUNTRY_CODES: readonly { code: string; name: string }[] = [
  { code: "+91", name: "India" },
  { code: "+1", name: "USA / Canada" },
  { code: "+44", name: "United Kingdom" },
  { code: "+971", name: "United Arab Emirates" },
  { code: "+966", name: "Saudi Arabia" },
  { code: "+974", name: "Qatar" },
  { code: "+965", name: "Kuwait" },
  { code: "+968", name: "Oman" },
  { code: "+973", name: "Bahrain" },
  { code: "+65", name: "Singapore" },
  { code: "+60", name: "Malaysia" },
  { code: "+61", name: "Australia" },
  { code: "+64", name: "New Zealand" },
  { code: "+880", name: "Bangladesh" },
  { code: "+977", name: "Nepal" },
  { code: "+94", name: "Sri Lanka" },
  { code: "+92", name: "Pakistan" },
  { code: "+975", name: "Bhutan" },
  { code: "+960", name: "Maldives" },
  { code: "+62", name: "Indonesia" },
  { code: "+66", name: "Thailand" },
  { code: "+84", name: "Vietnam" },
  { code: "+63", name: "Philippines" },
  { code: "+86", name: "China" },
  { code: "+81", name: "Japan" },
  { code: "+82", name: "South Korea" },
  { code: "+49", name: "Germany" },
  { code: "+33", name: "France" },
  { code: "+34", name: "Spain" },
  { code: "+39", name: "Italy" },
  { code: "+31", name: "Netherlands" },
  { code: "+27", name: "South Africa" },
  { code: "+234", name: "Nigeria" },
  { code: "+254", name: "Kenya" },
  { code: "+20", name: "Egypt" },
  { code: "+55", name: "Brazil" },
  { code: "+52", name: "Mexico" },
  { code: OTHER_CODE, name: "Other (type the country code too)" },
];

/** An Indian number: exactly 10 digits after +91 (D-083). */
export const PHONE_DIGITS = 10;

/** How many digits the number box takes: exactly 10 after +91 (D-083); after any other code what
 * the server's check allows, 8 to 15 digits in all with the code (E.164); after Other, the whole
 * number with its code. */
export function phoneDigits(cc: string): { min: number; max: number } {
  if (cc === "+91") return { min: PHONE_DIGITS, max: PHONE_DIGITS };
  const code = cc.replace(/\D/g, "").length;
  return { min: Math.max(1, 8 - code), max: 15 - code };
}

/** What is wrong with the digits typed after this country code, or "" (the server checks again). */
export function phoneProblem(cc: string, digits: string): string {
  if (!digits) return "";
  const { min, max } = phoneDigits(cc);
  if (digits.length < min || digits.length > max) {
    const wanted = min === max ? `exactly ${min}` : `${min} to ${max}`;
    return `Type ${wanted} digits (you typed ${digits.length}).`;
  }
  if (cc === OTHER_CODE && digits.startsWith("0"))
    return "Start with the country code, without 00 or +.";
  return "";
}

/** The words under the number box for this country code. */
export function phoneHint(cc: string): string {
  if (cc === "+91")
    return `${PHONE_DIGITS} digits, without the country code. Needed for phone call tasks.`;
  if (cc === OTHER_CODE) return "The whole number, starting with the country code.";
  return "Without the country code.";
}

/** Split a stored "+919876543210" into the list's code and the rest. A number whose code is not
 * listed is Other, holding the whole number; an empty one starts at India. */
export function splitPhone(phone: string | null | undefined): { cc: string; digits: string } {
  const value = (phone ?? "").trim().replace(/[^\d+]/g, "");
  if (!value.startsWith("+")) return { cc: "+91", digits: value.replace(/\D/g, "") };
  const match = COUNTRY_CODES.map((c) => c.code)
    .filter((code) => code !== OTHER_CODE && value.startsWith(code))
    .sort((a, b) => b.length - a.length)[0];
  const code = match ?? OTHER_CODE;
  return { cc: code, digits: value.slice(code.length).replace(/\D/g, "") };
}
