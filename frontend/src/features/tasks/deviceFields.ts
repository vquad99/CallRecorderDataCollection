// The device details a project may ask for each speaker (D-147), in the form's order, with their
// words: two texts and three Yes/No. The server's list is projects/moderation.DEVICE_FIELDS.
import type { DeviceField } from "../../api/projects";

export const DEVICE_FIELDS: readonly { key: DeviceField; label: string; yesNo: boolean }[] = [
  { key: "device_make", label: "Device make", yesNo: false },
  { key: "device_model", label: "Device model", yesNo: false },
  { key: "bluetooth_earphones", label: "Bluetooth earphones used", yesNo: true },
  { key: "wired_earphones", label: "Wired earphones used", yesNo: true },
  { key: "loudspeaker_on", label: "Loudspeaker on", yesNo: true },
];

/** The most characters of a device make or model (the server's MAX_DEVICE_TEXT). */
export const MAX_DEVICE_TEXT = 60;

export const deviceLabel = (key: DeviceField) =>
  DEVICE_FIELDS.find((f) => f.key === key)?.label ?? key;
