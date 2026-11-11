# Testing guide (for the client)

How to check the platform yourself, step by step, with what you should see after each step.
Screen labels are in **bold**. For more detail on any screen, see [USER_GUIDE.md](USER_GUIDE.md).

Website: **https://dubdesk.live** (Chrome or Edge on a computer).

## Test accounts

Four test accounts and a project called **Test project** (code `TEST`, face-to-face) are ready on
the live site. All four accounts are members of Test project.

| Role | Email |
|---|---|
| Project Admin | test.projectadmin@dubdesk.live |
| Moderator | test.moderator@dubdesk.live |
| QC Executive | test.qc@dubdesk.live |
| Client Viewer | test.client@dubdesk.live |

The passwords are sent to you separately; they are never written in this repository. The
`@dubdesk.live` addresses have no mailbox, so **Forgot your password?** does not work for these
four accounts; ask us for a new password instead.

One person can test every role: sign out (top right) and sign in as the next role.

## Main test: one recording from start to finish

| # | Sign in as | Do this | You should see |
|---|---|---|---|
| 1 | Project Admin | **Projects → Test project → Overview**. Type a short text in **Consent form text**. Click **Save project**. | The text is saved. |
| 2 | Project Admin | **Participants → Add participant**. Add two people with **your own email addresses**. **Language code**: choose one from the list. | Each gets a code such as P000001. |
| 3 | Project Admin | Click **Send** next to each participant. | An email "Consent form for Test project" arrives at each address. |
| 4 | (Participant) | Open each email's link. Tick **I have read and understood this form**. Click **I agree**. | The page shows **You agreed**. |
| 5 | Project Admin | **Participants**. Click **Approve** for both. | The consent shows **Agreed** and **Approved**. |
| 6 | Project Admin | **Tasks → New task**. Project **Test project**, mode **Face-to-face**, the two participants. Click **Create task**. | A task such as T000001 with status **Draft**. |
| 7 | Project Admin | On the task page, **Assign moderator**: choose Test Moderator. Click **Assign**. | Status **Assigned**. |
| 8 | Moderator | **Tasks** → open the task. Click **Start session**. | Status **In progress**. |
| 9 | Moderator | **Record consent**: click **Consent given** for both participants. | Both show consent given. |
| 10 | Moderator | **Open the recorder** (same box) **→ Allow microphone** (allow in the browser) **→ Start recording**. Talk for 1 to 2 minutes. **Stop and save**. | **Recording saved**, with the files listed. |
| 11 | Moderator | Open the task again. In **Check your recording**, click **Listen**, then **Send to QC**. | Status **Audio QC**. |
| 12 | Project Admin | Open the task. **Audio quality**: choose Test QC Executive. Click **Assign QC**. | The QC Executive is shown. |
| 13 | QC Executive | **Tasks** → open the task. Read the check results. Click **Listen**. | The recording plays. |
| 14 | QC Executive | **Your decision → Pass: send to the admin for final approval → Save decision**. | Status **Admin review**. |
| 15 | Project Admin | Open the task. In **Final approval**, click **Listen**, then **Approve**. | Status **Approved**. |
| 16 | Project Admin | **Recordings → Download with consent form**. | Three files download: the audio (.wav), the consent record (.html) and the details file (.json). |
| 17 | Client Viewer | Open the **Dashboard**. | **Collection progress** shows the recorded and approved time. |

## Extra checks

| # | Check | How | You should see |
|---|---|---|---|
| A | Return and record again | Repeat steps 6 to 13 with a new task. At step 14 choose **Return: record again**, reason **re record**. | Status **Returned**. The Project Admin sets it back to **Assigned** (**Change status**), and the Moderator records again. |
| B | Reject | At step 14 choose **Fail: reject the recording** with a reason. | Status **Rejected**. |
| C | Consent refused | At step 4 click **I do not agree**. | The Participants list shows **Did not agree**. |
| D | Roles are limited | Sign in as Client Viewer and look at the menu. | Only **Dashboard** and **Projects**; no Tasks, Participants or Users. |
| E | Quiet recording | Record 30 seconds of silence. | The automatic check flags silence (**Listen and decide** or **Failed**). |
| F | Private link | Open a participant's consent link in a private window after they answered. | Their own page only: no other participant, no staff pages. |
| G | Many tasks at once | **Tasks → New task**, choose Test project. Under **Add many tasks**, paste the first line `participant_a,participant_b,mode,priority,due_date,moderator` and one line with your two participant codes and `test.moderator@dubdesk.live` as moderator. **Check rows**, then **Add 1 tasks**. | **1 tasks added**; the new task is **Assigned** to Test Moderator. |

## Not in this version

Phone-call recording, downloads for the Client Viewer, transcription and installing as an app.
Telephony appears in some forms but cannot be used yet.

## Reporting a problem

Send us: the step number, the account you used, what you expected, what you saw, and a
screenshot. The time it happened helps us find it in the logs.
