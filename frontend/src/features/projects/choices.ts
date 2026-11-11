// Fixed lists for the dropdowns: languages and phone country codes (D-083).
import type { Language } from "../../api/projects";

/** Language codes the platform stores (ISO 639), with the name people pick from. */
export const LANGUAGES: readonly { code: string; name: string }[] = [
  { code: "hi", name: "Hindi" },
  { code: "en", name: "English" },
  { code: "en-IN", name: "English (India)" },
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
  { code: "si", name: "Sinhala" },
  { code: "ar", name: "Arabic" },
  { code: "fr", name: "French" },
  { code: "de", name: "German" },
  { code: "es", name: "Spanish" },
  { code: "pt", name: "Portuguese" },
  { code: "it", name: "Italian" },
  { code: "ru", name: "Russian" },
  { code: "tr", name: "Turkish" },
  { code: "zh", name: "Chinese" },
  { code: "ja", name: "Japanese" },
  { code: "ko", name: "Korean" },
  { code: "id", name: "Indonesian" },
  { code: "ms", name: "Malay" },
  { code: "th", name: "Thai" },
  { code: "vi", name: "Vietnamese" },
];

export const languageLabel = (code: string) => {
  const known = LANGUAGES.find((l) => l.code === code);
  return known ? `${known.name} (${code})` : code;
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

/** Phone country codes, India first. */
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
];

export const PHONE_DIGITS = 10;

/** Split a stored "+919876543210" into the dropdown's code and the 10-digit number. */
export function splitPhone(phone: string | null | undefined): { cc: string; digits: string } {
  const value = (phone ?? "").replace(/[^\d+]/g, "");
  const match = COUNTRY_CODES.map((c) => c.code)
    .filter((code) => value.startsWith(code))
    .sort((a, b) => b.length - a.length)[0];
  if (match) return { cc: match, digits: value.slice(match.length) };
  return { cc: "+91", digits: value.replace(/\D/g, "") };
}
