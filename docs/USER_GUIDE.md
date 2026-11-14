# User guide

Conversation Collection records two-person conversations, face to face, in the web browser. It
keeps each participant's consent, checks the sound quality on its own, and lets a person approve
or reject every recording.

Website: **https://dubdesk.live**. Use a current Google Chrome or Microsoft Edge on a computer.

Words in **bold** are the exact labels you see on screen.

---

## 1. Who does what

| Role | What they do | Menu they see |
|---|---|---|
| Super Admin | Everything: users, projects, settings | Dashboard, Projects, Tasks, Phone calls, Participants, Users, Settings, Audit log, System status |
| Project Admin | Runs projects they belong to: participants, tasks, who records, who checks, downloads | Dashboard, Projects, Tasks, Phone calls, Participants, Audit log |
| Moderator | Records conversations on tasks given to them | Dashboard, Projects, Tasks, Phone calls |
| QC Executive | Listens to recordings and approves or rejects them | Dashboard, Projects, Tasks |
| Client Viewer | Sees the progress of their projects | Dashboard, Projects |
| Participant | The person being recorded; has no login, uses a private link | (their own private page) |

People only see projects they have been added to. The Super Admin sees every project.

A project's page has tabs (Team, Participants, Audio rules, Languages, Retention, Export) for
the Super Admin and Project Admin only. Everyone else sees the project's **Overview**.

---

## 2. Signing in

**First time.** The Super Admin adds you. You get an email from **no-reply@dubdesk.live** with the
subject **"You have been invited to Conversation Collection"**. Click the link (it works for 72
hours), type a password twice (12 to 128 characters, not your email) and click **Set password**.
Then sign in at https://dubdesk.live with your email and password.

**Forgot your password.** On the sign-in page click **Forgot your password?**, type your email,
click **Send reset link**. The emailed link works for 30 minutes. At most 3 links per hour.

**Signed out by itself.** After 30 minutes without use, and after 12 hours in any case.

**Locked out.** After 5 wrong passwords in 15 minutes the account waits 15 minutes. You see
**"Too many failed sign-in attempts. Try again later."**

**Two-step sign-in.** With it, signing in needs your password and a 6-digit code from an
authenticator app on your phone (Google Authenticator, Microsoft Authenticator or another one).

- **Super Admin and Project Admin must have it.** The first time you sign in, the only page you
  get is **Set up two-step sign-in**. Type your password and click **Turn on two-step sign-in**.
  In the authenticator app choose to add an account and **scan the code** on the page. (No
  camera? Click **Cannot scan? Type the key instead**: type the key shown, or **Copy key**; on a
  phone, **Open in an authenticator app on this device** adds it for you.) Type the 6-digit code
  the app shows and click **Confirm**. The application opens.
- **Everyone else may turn it on**: click your name at the top right, then **My account →
  Two-step sign-in**, and do the same.
- **New phone:** on **My account**, turn it off with your password and a current code, then set
  it up again with the new phone.
- **Lost phone:** ask a Super Admin. On your user page they click **Reset two-step sign-in**. You
  are signed out everywhere; sign in with your password and set it up again. (For the last Super
  Admin, the person who runs the server uses `python -m app.cli reset-mfa <email>`.)

**My account** also has **Change password** and **Signed-in devices** (sign out other devices).

**Install the application.** On **My account**, **Install the application** puts Conversation
Collection among your applications: it then opens in its own window from the desktop or the
phone's home screen. Click **Install** when the button is there; otherwise the card says how to do
it in your browser (Chrome or Edge on a computer, Chrome on Android, Safari on iPhone). It still
needs a connection: nothing is kept on the device. Without a connection you see **You are
offline**; click **Try again** when it is back.

**A new version.** When the application has been updated while your page was open, a bar at the
bottom says **A new version of the application is ready**. Click **Reload** when you are not in
the middle of a recording, or **Later**.

**Sign out**: the **Sign out** button at the top right.

---

## 3. How a recording moves through the platform

| Step | Task status | Who | What happens |
|---|---|---|---|
| 1 | Draft | Project Admin | Creates the task with two participants |
| 2 | Assigned | Project Admin | Chooses the Moderator (status changes by itself) |
| 3 | In progress | Moderator | Starts the task |
| 4 | Recorded | Moderator | The recording is saved and checked automatically; the Moderator listens, then clicks **Send to QC** (or **Record again**) |
| 5 | Audio QC | QC Executive | Pass (goes to the admin), Fail (Rejected) or Return (record again) |
| 6 | Admin review | Project Admin | Listens and gives the final word: **Approve**, or Reject / send back with a reason |
| 7 | Approved | - | Done; the recording can be downloaded with its consent form |

A task can also be put **On hold** or **Cancelled** by the Project Admin, with a reason. A
**Returned** task goes back to the Moderator to record again. **Approved**, **Rejected** and
**Cancelled** are final.

---

## 4. Super Admin

### Users

**Users → Add user**: type **Email** and **Name**, tick one or more **Roles**, click **Add and send
invitation**. The person gets the invitation email and sets their own password. You never see or
set it.

**Users → Import CSV** adds many people. The file's first line must be exactly:

```
email,display_name,roles
```

Roles are written as codes: `SUPER_ADMIN`, `PROJECT_ADMIN`, `MODERATOR`, `QC_EXECUTIVE`,
`CLIENT_VIEWER`. Separate several roles with a semicolon. Click **Preview**, check the problems
column, then **Import N valid row(s)**. Up to 1000 rows.

Click a name to open the user. There you can change the name, email or roles (**Save changes**),
**Disable account** / **Enable account**, **Send password link** (a new invitation, or a reset link
if the password is already set), and **Sign out everywhere**. Users are never deleted, only
disabled.

**Phone calls → TxContact agent seat** (moderators only): type the moderator's TxContact agent ID
(for example `70001`) and click **Save agent seat**. Their phone calls ring that seat. Each seat
belongs to one person; leave it empty for moderators who do not make phone calls.

The number of active accounts is limited by **Settings → Staff accounts**.

**View as** (Super Admin only): on **Users**, click **View as [name]** to see the platform exactly
as that person does: their menu, their projects, their tasks. A yellow strip says who you are
viewing as. Nothing can be changed while viewing; every button that would save something is
refused. Click **Stop viewing** to return to your own view. Starting and stopping are in the
audit log under your own name.

To see a participant's own page, open the project's **Participants** tab and click **Their page**
on the row (Super Admin only). It is the page the participant sees, without the consent buttons.

### Projects

**Projects → New project** (only the Super Admin can create projects):

- The **project code** is given by the platform: `PRJ0001`, `PRJ0002`, and so on. You do not type it.
- **Name**, **Description**.
- **Recording modes allowed**: tick **Face-to-face** only. Phone calls are not available yet
  (section 11).
- **Face-to-face target (hours per day)**: the daily goal shown on dashboards.
- **Who may see participant phone numbers**.
- **Consent form text**: what participants read and agree to. A sample text is already filled in;
  change it to fit the project. Change **Consent policy version** whenever you change the text.

After **Create project** you return to the project list. A new project starts as **Draft**: click
its code to open it and use **Overview → Status → Change status to: Active**. Only **Active**
projects accept new tasks and recordings, and only they appear in **New task**.

Project tabs:

- **Overview**: the project settings and its status.
- **Team**: add people with **Add people**. A person's roles come from their account, so give a
  person the right role under Users first.
- **Participants**: the project's participants (section 5).
- **Audio rules**: the sound format and limits the automatic check uses (default 16 000 Hz,
  16-bit, mono, at most 25 % silence).
- **Languages**: the languages allowed for participants, chosen from a list (for example Hindi,
  Tamil, English (India)). When a project has languages, every participant must match one.
- **Retention**: how many days to keep each kind of file. Each box shows a faded example under it
  (for example `365` for one year); leave a box empty when there is no rule yet.

### Settings, System status, Audit log

- **Settings** (page title **Capacity targets**): planning targets. Only **Staff accounts** is
  enforced; it stops new accounts above the number.
- **System status**: shows whether the database, the work queue (redis) and file storage are
  reachable. Click **Check again** to refresh.
  **Needs attention** lists what the platform found wrong at its last look (it looks every
  minute): failed recordings, phone calls waiting for a person, failed exports, storage or the
  work queue not answering. When an alert address is set on the server, the same goes out
  by email.
- **Audit log**: every change, who made it and when. Read only.

---

## 5. Project Admin: participants

**Participants → Add participant**:

- **Name or label** (required).
- **Country code** (choose from the list; India +91 is first) and **Phone number** (optional;
  exactly 10 digits, without the country code).
- **Email address**: needed to email the consent form.
- **Language code** (required; choose from the list. When the project has languages, only those
  are listed).
- **Dialect**, **Internal notes** (optional).

Each participant gets a code such as `P000123`.

**Add existing participant** (on a project's **Participants** tab): adds someone who is already
in another of your projects, instead of creating them again. Search by code or name, then click
**Add**. They keep their code, details and consent history. Only people who speak one of the
project's languages are listed.

**Add many**: paste or choose a file whose first line is `name,phone,email,language,dialect`.
Click **Check rows**, then **Add N participants**. Up to 500 rows.

### Consent

1. Click **Send** next to a participant (or tick several and click **Send consent form**). The
   participant gets an email **"Consent form for <project name>"** with a private link.
2. The participant opens the link, reads the form, ticks **I have read and understood this form**
   and clicks **I agree** or **I do not agree**. They can later **Withdraw my consent**.
3. The **Consent form** column shows **Not answered**, **Agreed**, **Did not agree** or
   **Withdrawn**. When the answer is Agreed, click **Approve**, or **Reject** with a note that the
   participant will see.
4. **History** shows earlier answers.

### Everything about one participant

Click **View** on a participant's row. One panel shows all the platform holds about them in the
project:

- **Profile**: code, name, phone, email, language, notes, who added them and when, when they
  were last changed, and the projects they are in.
- **Work in this project**: sessions, recorded and approved conversations and minutes, payable
  minutes, phone calls made to them, calls with a recording, and the last call.
- **Personal link**: whether it works, who made it and when, until when it works, when it was
  last opened, and whether it was emailed or passed on by staff.
- **Consent form**: the answer, when, the form version, the review and its note, the form text,
  and earlier answers. **Download consent form** saves it.
- **Sessions**: every task they were part of, with their role (A or B), the other participant,
  the moderator, the status, the consent noted in that session, the recording length, and the
  number of phone calls. Click the task code to open the task.

A project's **Participants** tab also has **Personal link**: a link you can copy and give the
participant yourself (it works for 30 days; making a new one ends the old one).

### Other actions on ticked rows

- **Assign to project**: adds the participants to another project too.
- **Remove**: deletes the person's name, phone, email and notes everywhere. Not possible while
  they are on an open task.

---

## 6. Project Admin: tasks

**Tasks → New task**: choose **Project (active projects)**, **Recording mode: Face-to-face**,
**Participant A** and **Participant B** (two different people), **Priority**, **Moderator** (choose
now and the task starts as **Assigned**, or **Assign later**) and **Due date**, then **Create task**. Each task gets a code such as `T000045`.

If the project has fewer than two participants, the page says so and links to **Add participants
to the project**; add them first.

**Add many tasks** (on the same page, after choosing the project): paste or choose a CSV file, one
task per line. The first line must be exactly:

```
participant_a,participant_b,mode,priority,due_date,moderator
```

Write participants by their code (`P000001`). `mode` is `face_to_face` or `telephony` (empty means
face-to-face), `priority` is `low`, `normal`, `high` or `urgent` (empty means normal), `due_date` is
`YYYY-MM-DD`, and `moderator` is the moderator's email (the task is then assigned at once; empty
leaves it in Draft). **Download sample CSV** gives a file with the right first line and two example
rows to fill in. Click **Check rows**, then **Add N tasks**. Up to 500 rows.

On the task page:

- **Assign moderator**: choose the Moderator and click **Assign**. The task becomes **Assigned**.
- **Audio quality → Assign QC**: after the recording, choose the QC Executive who will check it.
  The person who recorded cannot check their own recording.
- **Change status**: put the task **On hold**, **Cancelled**, or back to **Assigned** after a
  return, with a reason.
- **History**: everything that happened; add a comment with **Add comment**.

### Downloads

On an approved task, in **Recordings**, click **Download with consent form**. You get three files:

1. The audio file (16 kHz WAV, ready for delivery).
2. The consent record (`consent_<task>_<recording>.html`): both participants' consent for this
   session and their own form answers, plus the audio file's checksum.
3. The details file (`metadata_<task>_<recording>.json`): the project, session, participants,
   device, every file with its measurements, the automatic check and the QC decision.

Downloads are available to the Super Admin and Project Admin.

---

## 7. Moderator: recording

1. Open **Tasks** and click your task.
2. Click **Start session** (the highlighted box near the top).
3. **Record consent**: choose **How consent was given**, then click **Consent given** (or
   **Refused**) on the row of Participant A and of Participant B.
4. Click **Open the recorder** (in the same highlighted box).
5. Click **Allow microphone** and allow it in the browser. Choose the **Microphone** if you have
   more than one, and watch the **Input level**.
6. Optional: **Test (5 s, then play back)** to hear yourself.
7. Place the microphone between the two speakers, no more than 2.5 feet from each, and do not move
   it.
8. Click **Start recording**. Talk. Keep the tab open and the computer awake. The audio uploads in
   small parts while you record.
9. Click **Stop and save**. Wait for **Recording saved**.
10. Go back to the task. In **Check your recording**, click **Listen**. If it is good, click
    **Send to QC**; if not, click **Record again** and record it once more.

The platform checks the sound within about a minute of saving; **Send to QC** works once that
check is done.

If the internet drops, recording carries on and the saved parts are sent when it comes back. If
the tab closes by mistake, open the recorder again: it offers **Keep the saved m:ss** or **Discard
it**. A recording can be up to 4 hours long.

---

## 7a. Moderator: phone calls

Phone calls go through TxContact. You need a **TxContact agent seat**: the Super Admin adds it on
your user page (**Users → your name → Phone calls → TxContact agent seat**). Sign in to your
TxContact agent screen before you start.

1. Open **Tasks** and click your **Telephony** task.
2. Click **Start session**.
3. Click **Start call**. TxContact rings participant A and connects them to your TxContact seat.
   The card shows **On the call** once TxContact has accepted the request; if it refused, the
   card says what TxContact answered.
4. In your TxContact agent screen, add participant B to the call.
5. Tick the **Call checklist** as you go: **Participant A is on the call**, **Participant B is on
   the call** (both are needed to close the call), **I am muted and listening**, **Both voices are
   clear**.
6. **Record consent** for Participant A and Participant B on the task page, as for face-to-face.
7. Stay on the call, **muted**, and listen. If the line is poor (noise, echo, breaking up), tell
   them, end the call, then click **Cancel this call** and choose **Poor line quality**.
8. When they have finished, click **Close call** (add a note if useful). If someone refused
   consent, click **Cancel this call** and choose **Consent refused**: they are not called again
   for this task.
9. The card shows **Fetching the recording**. The platform finds the call at TxContact and
   downloads its recording, usually within a few minutes. The page updates on its own. You can
   still cancel the call while it is being fetched.
10. When it arrives, the task moves to **Recorded**. Click **Listen**; if it is good, **Send to
    QC**; if not, **Call again**.

If the call did not work (no answer, wrong number, dropped), click **Cancel this call** and choose
the reason. You can then start a new call. A task can be called at most 6 times in an hour.

**Needs a person to pick the recording.** If several TxContact calls fit the time, or none shows
participant A's number, the card lists them with their start time, length and the last two digits
of each number. Click **This is the call** on the right one. If none was found, or TxContact could
not be searched (the card says why), click **Look for the recording again** later, or cancel the
call. A project admin can do the same, and cancel a call, from the task's **Phone calls** history.

**Phone calls page.** The menu has **Phone calls** (Super Admin, Project Admin, Moderator). A
moderator's page is **My phone calls**: the list of their own calls, newest first, each with a
link to its task. Admins choose a **Project** and a **Period** (7, 30 or 90 days) and see:

- **Figures**: calls; recorded (and the share of calls); failed or cancelled; **needs a person**
  (also calls left open); average call; recorded audio and how long recordings take to arrive;
  **Today** against the project's daily telephony target; phone tasks **not called yet**.
- **Calls per day** (recorded, still open, failed or cancelled), with a table view.
- **From call to approval**: calls started, accepted by TxContact, closed by the moderator,
  recording stored, tasks sent to QC, tasks approved.
- **Phone tasks by status**, **Calls by hour of the day**, **By moderator**, and **By project**
  when you look at all your projects.
- **Automatic audio check** and **QC decisions** on call recordings.
- **Why calls were cancelled**, **Problems getting the recording**, and the **Call checklist on
  closed calls** (how often each box was ticked).
- Project admins also see **TxContact: calls per hour**, TxContact's own count for the account.
- **All calls**: every call with a link to its task; **Show** filters it (for example **Needs a
  person**). **Download calls (CSV)** saves the period's calls as a spreadsheet.

Moderators have no figures, charts or CSV: only the list of their own calls. No page shows a
full phone number: the last two digits only.

**Phone calls history.** Every task shows each call with every step: when it was requested, what
TxContact answered, each checklist tick, when it was closed, each search, which recording was
chosen and when it was stored. The recording's details file (in **Download with consent form** and
in the project's metadata export) carries the same history in its **call** section.

---

## 8. QC Executive: checking a recording

1. Open **Tasks** (set **Status: Audio QC** to see only waiting work), or your **Dashboard**.
2. Open the task. The **Audio quality** card shows the automatic check: overall **Passed**,
   **Listen and decide** or **Failed**, and a row for each check (format, length, silence,
   clipping, loudness, duplicates and more).
3. Click **Listen** to hear the recording.
4. Under **Your decision**, choose:
   - **Pass: send to the admin for final approval** → the task becomes **Admin review**;
   - **Return: record again** → back to the Moderator;
   - **Fail: reject the recording** → **Rejected**.

   For Return or Fail, pick a **Reason**. A **Comment** is required when you pass a recording the
   automatic check failed, or when the reason is "other".
5. Click **Save decision**.

**Check the stored file again** repeats the automatic check on the stored file.

The automatic check never approves or rejects anything by itself; a person always decides.

### Project Admin: final approval

A task that passed QC shows **Admin review**. Open it: the **Final approval** card lets you
**Listen** and **Approve**. To reject it or send it back for a new recording, use **Change
status** with a reason. Only then is the task **Approved** and ready to download.

**Many at once** (Tasks list): tick the tasks (or the box at the top of the list for the whole
page). A bar appears with:

- **Approve selected (N)**: approves the ticked tasks that are waiting for admin review; the others
  are skipped and named.
- **Clear**: removes the ticks.

### Export a project

Open the project and click the **Export** tab (Super Admin and Project Admin).

**Recordings** are exported as one ZIP, prepared in the background:

1. Choose **What to export**: **Audio + metadata**, **Audio only** or **Metadata only**.
2. Choose **Which recordings**: **Approved tasks only** (the delivery) or **Every finished
   recording**. You can narrow it by **Recording type** (face-to-face or telephony), **Language**,
   and the days it was recorded (**Recorded from**, **Recorded to**; days in India time).
3. Choose **Tables as** CSV or TSV.
4. Optional: **Also include the original recordings** (as recorded, before any processing; much
   larger). Super Admin only: **Also include names, phone numbers and email addresses**. Without
   it, participants appear by code only.
5. The page shows how many recordings fit and how much audio. Click **Prepare export**.
6. The export appears under **Prepared exports**: **Waiting**, **Being prepared**, then **Ready**.
   The page checks by itself; you can leave it and come back.
7. Click **Download**. The link works for 5 minutes; click again for a new one. A prepared
   export is kept for 24 hours, then removed. **Remove** takes it away sooner.

If an export shows **Failed**, the reason is written under its name. Prepare it again; if it
fails again, tell the Super Admin.

What is in the ZIP:

| Folder or file | What it is |
|---|---|
| `face_to_face/`, `telephony/` | One folder per kind of recording. Inside each: `audio/` (16 kHz WAV), `originals/` (if asked for), `metadata/` (details file, JSON), `consent/` (consent record) |
| `recordings.csv` or `.tsv`, `recordings.json` | One row per recording: task, mode, language, people by code, consent, length, checks, file names and checksum |
| `participants.csv` or `.tsv` | The people in these recordings, by code |
| `manifest.json`, `manifest.csv`, `SHA256SUMS` | Every file with its size and checksum. The receiver can check the files with `sha256sum -c SHA256SUMS` |
| `schema/`, `README.txt` | The description of the JSON files, and a short explanation |

There are no transcripts in an export: this version makes none.

**Reports** are one table each, saved at once as **CSV** or **TSV**:

| Report | You get |
|---|---|
| **Progress report** | A row per task with status, participants, moderator, QC, recording length, checks, approval date and phone calls |
| **Participant minutes** | A row per participant with conversations, recorded minutes, approved minutes and payable minutes |

### Participant minutes (payment)

Payment follows **approved** audio. Every conversation has two participants, so each one is
credited with half of it: a 5-minute approved conversation gives each participant **2.5 payable
minutes**. A re-recorded task counts once (its newest finished recording). Project Admins see the
**Recorded min**, **Approved min** and **Payable min** columns on the project's **Participants**
tab; the **Participant minutes** export gives the same numbers as a spreadsheet.

---

## 9. Client Viewer: progress

The **Dashboard** (**Collection progress**) shows recorded and approved hours, today's hours
against the daily target, and an hours-per-day chart. Choose a **Project** and a **Period** (last 7,
30 or 90 days, or **Chosen days** with a first and a last day). You can narrow it by **Recording
type** and **Language** (and **Dialect**, when the project has any). Days are counted in India
Standard Time.

### Dashboard filters (everyone)

Under the page title is a row of filters. Each one narrows every figure on the page:

| Filter | Who has it | What it does |
|---|---|---|
| **Project**, **Period** | everyone | One project or all of yours; the last 7, 30 or 90 days, or **Chosen days** |
| **From**, **To** (with Chosen days) | everyone | Counts only recordings started on those days; the chart shows exactly those days. At most 366 days |
| **Recording type** | everyone | Face-to-face or telephony |
| **Language**, **Dialect** | everyone | Conversations in which a participant speaks it |
| **Task status** | staff | Tasks in that status |
| **Staff** | Super Admin, Project Admin | One person's tasks and the recordings they made |

**Clear filters** takes them all off. Without chosen days the totals at the top count
everything ever recorded; with chosen days they count those days only.

Managers also see **Phone calls**: placed, recorded, could not be placed, waiting for a person,
still open.

---

## 10. Participant: the private page

The participant opens the link from the consent email. No login is needed. The page shows:

- **Your details**: code, name, language, dialect and the last two digits of the phone number.
  Read-only; to correct anything the participant contacts the project team.
- **Minutes**: sessions, recorded time, accepted time, and **Your share for payment** (half of
  each accepted conversation).
- **Consent form**: read it, tick **I have read and understood this form**, click **I agree** or
  **I do not agree**. After agreeing they can **Withdraw my consent**.
- **Your sessions**: each session and its state (**Planned**, **Recorded, being checked**,
  **Accepted**, **To be recorded again**, **Not used**).

The link works for 30 days. If it stops working, the project team sends a new one.

---

## 11. Not available in this version

- **Phone calls are new and not yet tested on the TxContact account.** Try one test call (section
  7a) before real work. Whether a second person can be added to a call, and whether the two
  speakers are recorded apart, is for TxContact to confirm.
- **Transcription.**
- **Installing as an app** on a phone or computer.

---

## 12. Problems and fixes

| What you see | What to do |
|---|---|
| "Microphone permission was refused" | Click the lock icon in the address bar, allow the microphone, reload. |
| "No microphone was found" | Connect a microphone, then choose it again. |
| "This browser cannot record here" | Use the latest Chrome or Edge on a computer. |
| New task: **Create task** stays grey | Choose both participants. If the lists are empty, the project needs at least two participants: use **Add participants to the project**. |
| "Unexpected Application Error" / "Failed to fetch dynamically imported module" | The site was updated while the page was open. The page now reloads by itself; if the message stays, press Ctrl+Shift+R (Cmd+Shift+R on a Mac). |
| "The task must be in progress to record" | Moderator: **Change status → In progress → Apply**. |
| "This link is invalid or has expired" | Ask for a new link: **Forgot your password?**, or the admin's **Send password link**. |
| "Too many failed sign-in attempts" | Wait 15 minutes, then try again or reset the password. |
| No invitation or consent email | Check spam. Emails come from no-reply@dubdesk.live. |
| "No access" | Your role does not include that page. Ask an administrator. |
| The site does not open on one computer only | That computer still remembers an old address. Wait a few hours or restart the router. |
