// Speaker details (D-143): the lists the participant form offers and the words for the codes. The
// server checks every value (backend/app/modules/participants/speakers.py); a backend test checks
// that the states and codes here are the ones it accepts.
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

export const MIN_AGE = 20;
export const MAX_AGE = 60;

/** Every speaker detail with its label, in the form's order; `district` is the native district. */
export const SPEAKER_FIELDS: readonly { key: keyof SpeakerDetails | "district"; label: string }[] =
  [
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

/** The labels of the details these fields do not have yet. */
export function missingSpeakerDetails(f: SpeakerDetails & Pick<ParticipantFields, "district">) {
  return SPEAKER_FIELDS.filter(({ key }) => {
    const value = f[key];
    return value === null || value === undefined || String(value).trim() === "";
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

/** What is wrong with a typed age, or nothing. */
export const ageProblem = (value: number | null) =>
  value !== null && !(Number.isInteger(value) && value >= MIN_AGE && value <= MAX_AGE)
    ? `Age must be a whole number from ${MIN_AGE} to ${MAX_AGE}.`
    : undefined;
