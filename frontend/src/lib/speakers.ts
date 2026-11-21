// Speaker details (D-143): the lists the participant form offers and the words for the codes. The
// server checks every value (backend/app/modules/participants/speakers.py); a backend test checks
// that the states, codes and fields here are the ones it knows. What a project asks of its
// speakers - their ages and the details needed before a task - is the project's own rule (D-145).
import type { ParticipantFields, SpeakerDetails } from "../api/work";

/** The 28 states and 8 union territories of India. */
export const INDIAN_STATES = [
  "Andaman and Nicobar Islands",
  "Andhra Pradesh",
  "Arunachal Pradesh",
  "Assam",
  "Bihar",
  "Chandigarh",
  "Chhattisgarh",
  "Dadra and Nagar Haveli and Daman and Diu",
  "Delhi",
  "Goa",
  "Gujarat",
  "Haryana",
  "Himachal Pradesh",
  "Jammu and Kashmir",
  "Jharkhand",
  "Karnataka",
  "Kerala",
  "Ladakh",
  "Lakshadweep",
  "Madhya Pradesh",
  "Maharashtra",
  "Manipur",
  "Meghalaya",
  "Mizoram",
  "Nagaland",
  "Odisha",
  "Puducherry",
  "Punjab",
  "Rajasthan",
  "Sikkim",
  "Tamil Nadu",
  "Telangana",
  "Tripura",
  "Uttar Pradesh",
  "Uttarakhand",
  "West Bengal",
] as const;

export const GENDER_LABELS: Record<string, string> = {
  MALE: "Male",
  FEMALE: "Female",
};

export const EDUCATION_LABELS: Record<string, string> = {
  PRIMARY: "Primary School",
  SECONDARY: "Secondary School",
  HIGHER_SECONDARY: "Higher Secondary",
  DIPLOMA: "Diploma",
  BACHELORS: "Bachelor's Degree",
  MASTERS: "Master's Degree",
  PHD: "PhD",
  OTHER: "Other",
};

export const EDUCATION_MEDIUM_LABELS: Record<string, string> = {
  ENGLISH: "English",
  NON_ENGLISH: "Non-English",
};

/** A speaker detail's name, as the server and the project's rules know it. */
export type SpeakerKey = keyof SpeakerDetails | "district";

/** Any person's age; a project narrows it to the speakers it takes (D-145). */
export const AGE_LIMITS = { min: 1, max: 120 } as const;

/** Every speaker detail with its label, in the form's order; `district` is the native district. */
export const SPEAKER_FIELDS: readonly { key: SpeakerKey; label: string }[] = [
  { key: "age", label: "Age" },
  { key: "gender", label: "Gender" },
  { key: "current_state", label: "Current state" },
  { key: "current_district", label: "Current district" },
  { key: "current_pincode", label: "Current PIN code" },
  { key: "native_state", label: "Native state" },
  { key: "district", label: "Native district" },
  { key: "native_pincode", label: "Native PIN code" },
  { key: "native_language", label: "Native language" },
  { key: "education", label: "Education" },
  { key: "education_medium", label: "Medium of education" },
  { key: "recording_state", label: "Recording state" },
  { key: "recording_district", label: "Recording district" },
  { key: "recording_pincode", label: "Recording PIN code" },
];

/** A participant's speaker details as the form holds them (null where not given or not shown). */
export const speakerDetailsOf = (p: Partial<SpeakerDetails>): SpeakerDetails => ({
  age: p.age ?? null,
  gender: p.gender ?? null,
  current_state: p.current_state ?? null,
  current_district: p.current_district ?? null,
  current_pincode: p.current_pincode ?? null,
  native_state: p.native_state ?? null,
  native_pincode: p.native_pincode ?? null,
  native_language: p.native_language ?? null,
  education: p.education ?? null,
  education_medium: p.education_medium ?? null,
  recording_state: p.recording_state ?? null,
  recording_district: p.recording_district ?? null,
  recording_pincode: p.recording_pincode ?? null,
});

export const EMPTY_SPEAKER_DETAILS = speakerDetailsOf({});

/** The speaker details side by side as the participant form groups them (and the Rules tab). */
export const SPEAKER_GROUPS: readonly { title: string; keys: readonly SpeakerKey[] }[] = [
  { title: "Age and gender", keys: ["age", "gender"] },
  { title: "Where they live now", keys: ["current_state", "current_district", "current_pincode"] },
  { title: "Where they were born", keys: ["native_state", "district", "native_pincode"] },
  { title: "Language", keys: ["native_language"] },
  { title: "Education", keys: ["education", "education_medium"] },
  {
    title: "Where the recording takes place",
    keys: ["recording_state", "recording_district", "recording_pincode"],
  },
];

export const speakerLabel = (key: string) =>
  SPEAKER_FIELDS.find((f) => f.key === key)?.label ?? key;

/** What a project asks of its speakers (D-145): the ages it takes and the details needed before a
 * task. */
export interface SpeakerRules {
  minAge: number;
  maxAge: number;
  required: readonly string[];
}

/** Without a project (none chosen yet): any person's age, nothing needed. */
export const NO_PROJECT_RULES: SpeakerRules = {
  minAge: AGE_LIMITS.min,
  maxAge: AGE_LIMITS.max,
  required: [],
};

export const speakerRulesOf = (p: {
  speaker_min_age: number;
  speaker_max_age: number;
  required_speaker_details: readonly string[];
}): SpeakerRules => ({
  minAge: p.speaker_min_age,
  maxAge: p.speaker_max_age,
  required: p.required_speaker_details,
});

/** The labels of the details the project needs that these fields do not have yet. */
export function missingSpeakerDetails(
  f: SpeakerDetails & Pick<ParticipantFields, "district">,
  required: readonly string[],
) {
  return SPEAKER_FIELDS.filter(({ key }) => {
    const value = f[key];
    return (
      required.includes(key) &&
      (value === null || value === undefined || String(value).trim() === "")
    );
  }).map(({ label }) => label);
}

/** A place in one line ("North Goa, Goa 403001"), or "-" when nothing is given. */
export const placeText = (
  state: string | null | undefined,
  district: string | null | undefined,
  pincode: string | null | undefined,
) => [[district, state].filter(Boolean).join(", "), pincode].filter(Boolean).join(" ") || "-";

/** What is wrong with a typed PIN code, or nothing. */
export const pincodeProblem = (value: string | null) =>
  value && !/^[1-9][0-9]{5}$/.test(value)
    ? "Type the 6 digits of the PIN code; it cannot start with 0."
    : undefined;

/** What is wrong with a typed age for this project, or nothing (the server checks again). */
export const ageProblem = (value: number | null, rules: SpeakerRules) =>
  value !== null && !(Number.isInteger(value) && value >= rules.minAge && value <= rules.maxAge)
    ? `Age must be a whole number from ${rules.minAge} to ${rules.maxAge}.`
    : undefined;
