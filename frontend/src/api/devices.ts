// The device each speaker used in a conversation (D-147): filled by the task's moderator (or a
// project admin) before the task goes to QC, read only afterwards. Loaded with the task and
// recorder pages only, not with the first screen.
import { apiRequest } from "./client";
import type { DeviceField } from "./projects";

export type { DeviceField };

/** One speaker's device details; null = not answered. */
export interface DeviceValues {
  device_make: string | null;
  device_model: string | null;
  bluetooth_earphones: boolean | null;
  wired_earphones: boolean | null;
  loudspeaker_on: boolean | null;
}

export interface DeviceParty {
  side: "A" | "B";
  participant_id: string;
  participant_code: string;
  details: DeviceValues;
  filled_by: string | null;
  filled_at: string | null;
  /** The asked details not answered yet. */
  missing: DeviceField[];
  /** The person's newest details on another task of the project, offered to whoever may fill
   * them ("Same as last time"); never filled in by itself. */
  last_time: (DeviceValues & { task_code: string; filled_at: string }) | null;
}

export interface DeviceDetails {
  /** The details the project asks, in the form's order. */
  fields: DeviceField[];
  call_type: "Telephonic" | "Face-to-face";
  /** The caller may change them now (the task's moderator or an admin, before QC). */
  editable: boolean;
  complete: boolean;
  participants: DeviceParty[];
}

export const getDeviceDetails = (taskId: string) =>
  apiRequest<DeviceDetails>(`/api/v1/tasks/${taskId}/device-details`);

/** Both people's details at once, by side. */
export const saveDeviceDetails = (
  taskId: string,
  participants: (DeviceValues & { side: "A" | "B" })[],
) =>
  apiRequest<DeviceDetails>(`/api/v1/tasks/${taskId}/device-details`, {
    method: "PUT",
    body: { participants },
  });
