# User guide

Conversation Collection records two-person conversations, face to face, in the web browser. It
keeps each participant's consent, checks the sound quality on its own, and lets a person approve
or reject every recording.

Website: **https://dubdesk.live**. Use a current Google Chrome or Microsoft Edge on a computer.

Words in **bold** are the exact labels you see on screen.

Dates and times are in India time, written the Indian way, for example 17 Nov 2026, 1:57 pm.

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

A project's page has tabs (Team, Participants, Tasks, Audio rules, Languages, Retention, Export) for
the Super Admin and Project Admin only. Everyone else sees the project's **Overview**.

---

## 2. Signing in

**First time.** The Super Admin adds you. You get an email from **no-reply@dubdesk.live** with the
subject **"You have been invited to Conversation Collection"**. Click the link (it works for 72
hours), type a password twice (12 to 128 characters, not your email) and click **Set password**.
Then sign in at https://dubdesk.live with your email and password.

**Forgot your password.** On the sign-in page click **Forgot your password?**, type your email,
click **Send reset link**. The emailed link works for 30 minutes. At most 3 links per hour.

**Signed out by itself.** After 10 minutes without use, and after 12 hours in any case. An open recording or phone call keeps you signed in.
One minute before, a strip says **You will be signed out in 1 minute.** Click **Stay signed in**
to carry on.

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

**My account** also has **Change password** and **Signed-in devices**: each device is shown like
"Edge on Windows · 127.0.0.1"; **Sign out** signs out another device.

**Phone seat** (moderators who make phone calls): **My account** shows your **Seat number** and
your **Seat password**, hidden. Click **Show** to see the password, **Hide** to cover it again.
You do not need them to make calls: the portal signs your phone line in by itself (section
7a). You need them only if your admin asks you to use TxContact's Chirp app. Each time you
click **Show**, it is written in the audit log.
No seat, or no password yet? Ask your Super Admin.

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
| 5 | Audio QC | QC Executive | Pass (goes to the admin) or Reject |
| 6 | Admin review | Project Admin | Listens and gives the final word: **Approve** or **Reject** with a reason |
| 7 | Approved | - | Done; the recording can be downloaded with its consent form |

A task can also be put **On hold** or **Cancelled** by the Project Admin, with a reason.
**Approved**, **Rejected** and **Cancelled** are final. There is no "send back to record again":
to record a rejected conversation again, create a new task.

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

**Phone calls → Phone seat** (moderators only): on the moderator's user page, under **Phone
calls**, type the seat number TxContact gave for them (for example `80003`) in **Seat number**,
and the seat's password from TxContact in **Seat password**. Click **Save phone seat**. Their
phone calls go through that seat. While they are signed in, the portal signs their phone
line in with the seat number and password by itself: they do not need the Chirp app.
One seat per person; leave **Seat number** empty for moderators who do not make phone calls
(this also removes the password). The **Users** list shows each seat in the **Phone seat** column.

- The password is saved in secret form. To change it, type the new one and save. Leave **Seat
  password** empty to keep the saved password.
- To see the saved password, click **Show** next to **Saved password**. Each time is written in
  the audit log. The moderator can also see it on their own **My account** page.

The number of active accounts is limited by **Settings → Staff accounts**.

**View as** (Super Admin only): on **Users**, click **View as** on a person's row to see the
platform exactly as that person does: their menu, their projects, their tasks. A yellow strip says
who you are viewing as. Nothing can be changed while viewing; every button that would save
something is refused. Click **Stop viewing** to return to your own view. Starting and stopping are in the
audit log under your own name.

To see a participant's own page, open the project's **Participants** tab and click **Their page**
on the row (Super Admin only). It is the page the participant sees, without the consent buttons.

### Projects

**Projects → New project** (only the Super Admin can create projects):

- The **project code** is given by the platform: `PRJ0001`, `PRJ0002`, and so on. You do not type it.
- **Name**, **Description**.
- **Recording types allowed**: tick **Face-to-face**, **Phone call**, or both. Phone calls are new:
  read section 11 first.
- **Phone call target** and **Face-to-face target (hours per day)**: the daily goals shown on
  dashboards.
- **Who may see participant phone numbers**.
- **Consent form text**: what participants read and agree to. A sample text is already filled in;
  change it to fit the project. Change **Consent policy version** whenever you change the text.

After **Create project** you return to the project list. A new project starts as **Draft**: click
its code to open it and, on **Overview → Status**, click **Make active**. Only **Active**
projects accept new tasks and recordings, and only they appear in **New task**.

The **Status** card has a button for each next step: **Make active**, **Pause**, **Mark as
completed**, **Archive**, and **Reopen** for a completed or archived project. Each asks you to
confirm; archiving or reopening also needs a reason.

Project tabs:

- **Overview**: the project settings and its status.
- **Team**: add people with **Add people**. A person's roles come from their account, so give a
  person the right role under Users first.
- **Participants**: the project's participants (section 5).
- **Tasks**: every task of this project, with the same search, status and recording type filters
  as the Tasks page. **New task** here starts with this project already chosen.
- **Audio rules**: the sound format and limits the automatic check uses. Defaults: face-to-face
  16 000 Hz, 16-bit, mono; phone calls 16 000 Hz, 16-bit, stereo (TxContact records calls in
  stereo). Both allow at most 25 % silence. A phone recording with one channel fails the check
  with "A track is missing".
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
- **Audit log**: every change, who made it and when. Read only. Narrow it with **Area**, **About**
  and **Action**; the values before and after a change are in a closed **Before and after**
  section on each row.

---

## 5. Project Admin: participants

**Participants → Add participant** (opens a window):

- **Name or label** (required).
- **Country code** (choose from the list; India +91 is first) and **Phone number** (optional;
  exactly 10 digits, without the country code).
- **Email address** (required): the consent form is sent there. It cannot be removed; someone
  added before emails were required gets one the next time they are edited.
- **Language** (required; choose from the list. When the project has languages, only those
  are listed).
- **Dialect**, **Internal notes** (optional).

Each participant gets a code such as `P000123`.

To change someone's details, click **Edit** on their row. A window **Edit P000123** opens; change
the details and click **Save changes**.

**Add existing participant** (on a project's **Participants** tab): adds someone who is already
in another of your projects, instead of creating them again. Search by code or name, then click
**Add**. They keep their code, details and consent history. Only people who speak one of the
project's languages are listed. To add many at once, tick the boxes (or **Select all shown**)
and click **Add selected**.

**District**: each participant can have a district (on the form and in the file). The dashboard
can be filtered by it.

**Add many**: paste or choose a file whose first line is
`name,phone,email,language,dialect,district` (`district` may be left out). Every row needs
an email.
Click **Check rows**, then **Add N participants**. Up to 500 rows.

### Consent

1. You do not send the consent form. When you add a participant to a project (one, many from a
   file, an existing one, or **Add to that project**), the platform emails them the project's
   consent form: **"Consent form for <project name>"** with a private link. The message after
   adding says so: **Consent form emailed.**
2. If the project has no consent form text yet, nothing is sent. The message says **Write the
   project's consent form, then send it.** Write it on the project page, then click **Email
   consent form again** for each person.
3. The participant opens the link, reads the form, ticks **I have read and understood this form**
   and clicks **I agree** or **I do not agree**. **I agree** counts at once: nobody approves it.
   It is final: there is no way to withdraw it. Someone who clicked **I do not agree** can still
   agree later.
4. The **Consent form** column shows **No answer yet**, **Agreed** or **Did not agree**.
5. Email lost? Click **Email consent form again** on the participant's row. It is only there
   until they agree.
6. **Consent history** shows earlier answers, in a window.
7. You can make a task only with people who have agreed (see section 6).

### Everything about one participant

Click **View** on a participant's row. One window shows all the platform holds about them in the
project:

- **Profile**: code, name, phone, email, language, notes, who added them and when, when they
  were last changed, and the projects they are in.
- **Work in this project**: sessions, recorded and approved conversations and minutes, payable
  minutes, phone calls made to them, calls with a recording, and the last call.
- **Personal link**: whether it works, who made it and when, until when it works, when it was
  last opened, and whether it was emailed or passed on by staff.
- **Consent form**: the answer, when, the form version, the form text, and earlier answers.
  **Download consent form** saves it.
- **Sessions**: every task they were part of, with their role (A or B), the other participant,
  the moderator, the status, the recording length, and the number of phone calls. Click the task
  code to open the task.

A project's **Participants** tab also has **Personal link**: a window with a link you can copy
(**Copy link**) and give the participant yourself (it works for 30 days; making a new one ends the
old one).

### Other actions on ticked rows

- **Also add them to another project**: choose the other project and click **Add to that project**. They stay in this project too, with the same code and consent history. Each one is emailed the other project's consent form; the list under the buttons says what happened to each.
- **Remove**: deletes the person's name, phone, email and notes everywhere. Not possible while
  they are on an open task.

---

## 6. Project Admin: tasks

**Tasks → New task**: choose **Project (active projects)**, **Recording type** (**Face-to-face**,
or **Phone call** when the project allows it),
**Participant A** and **Participant B** (two different people), **Priority**, **Moderator** (choose
now and the task starts as **Assigned**, or **Assign later**) and **Due date**, then **Create task**. Each task gets a code such as `T000045`.

Only people who agreed to the project's consent form can be chosen. When someone is left out,
the page says **Only people who agreed to the consent form can be chosen.** If the project has
fewer than two participants, the page says so and links to **Add participants to the project**;
add them first.

**Add many tasks** (on the same page, after choosing the project): paste or choose a CSV file, one
task per line. The first line must be exactly:

```
participant_a,participant_b,mode,priority,due_date,moderator
```

Write participants by their code (`P000001`); both must have agreed to the consent form, or
the row says who has not. `mode` is `face_to_face` or `telephony` (a phone
call; empty means face-to-face), `priority` is `low`, `normal`, `high` or `urgent` (empty means
normal), `due_date` is `YYYY-MM-DD`, and `moderator` is the moderator's email (the task is then assigned at once; empty
leaves it in Draft). **Download sample CSV** gives a file with the right first line and two example
rows to fill in. Click **Check rows**, then **Add N tasks**. Up to 500 rows.

On the task page:

- **Assign moderator**: choose the Moderator and click **Assign**. The task becomes **Assigned**.
  This is refused while one of the two has not agreed to the consent form.
- **Buttons at the top of the task page**: **Put on hold** and **Cancel task** each open a window
  with a **Reason** and a **Comment** (**Go back** closes it without a change). A task on hold
  shows **Resume task**, which puts it back where it was.
- **Delete task** (also at the top): for a task made by mistake. Type the reason. Only a
  task with no recording, phone call or consent noted on it can be deleted; otherwise cancel it
  instead.
- **QC is assigned by itself**: when the recording reaches Audio QC, the platform gives it to the
  project's active QC Executive with the fewest tasks waiting (in turn when equal), never the
  moderator or whoever recorded. If the project has no QC Executive free, nobody is set.
- **Audio quality → Assign QC**: to choose or change the QC Executive by hand. The person who
  recorded cannot check their own recording.
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
3. Consent is taken automatically from each participant's own consent form: you do not tick it.
   A task is only made for two people who agreed, so you normally see **Agreed** for both. On an
   older task where someone has not agreed, a **Waiting for consent** card lists them; people who
   manage participants can click **Email consent form again** there. A moderator asks their
   admin. **Open the recorder stays grey until both participants have agreed.**
4. Click **Open the recorder** (in the same highlighted box). The recorder shows the steps
   **Microphone**, **Sound check**, **Record**, **Save**, **Done**; **Back to the task** is above
   them. It records at 16000 Hz (the project's rate).
5. Click **Allow microphone** and allow it in the browser. Choose the **Microphone** if you have
   more than one, and watch the **Input level**.
6. Optional: **Test (5 s, then play back)** to hear yourself.
7. Place the microphone between the two speakers, no more than 2.5 feet from each, and do not move
   it.
8. Click **Start recording**. Talk. Keep the tab open and the computer awake. The audio uploads in
   small parts while you record.
9. Click **Stop and save**. Wait for **Recording saved**.
10. On the same screen, click **Listen**. If it is good, click **Send to QC**; if not, click
    **Record again** and record it once more. (The same buttons are also on the task page.)
    After **Send to QC** the task page says **Sent to QC. A QC Executive checks it next.**

The platform checks the sound within about a minute of saving; **Send to QC** works once that
check is done.

If the internet drops, recording carries on and the saved parts are sent when it comes back. If
the tab closes by mistake, open the recorder again: it offers **Keep the saved m:ss** or **Discard
it** (it asks you to confirm; the saved audio is then deleted). A recording can be up to 4 hours
long.

---

## 7a. Moderator: phone calls

You start, follow and end every call on the task page in this portal. Your phone seat is set by
the Super Admin (section 4); if calls do not start, ask them.

**Your phone line.** When you sign in, the portal connects your phone seat to the phone system
and makes it ready for calls by itself. You do not click anything and you do not need the Chirp
app. The top of every page shows:

- **Phone line: Ready**: you can start a call.
- **Phone line: Connecting…**: wait a few seconds.
- **Phone line: On a call**: a call is open. When you close or cancel it, the line is ready again
  for the next call.
- **Phone line not connected:** and the reason: click **Try again**. If it fails again, ask your
  admin to check your seat number and password.

The line goes offline when you sign out, when you are signed out after 10 minutes without use,
and when you close the tab. Opening the portal again connects it again. No seat password saved
yet? The call card says **Ask your admin to save your phone seat password.**

1. Open **Tasks** and click your **Phone call** task.
2. Click **Start session**. The card says **Ready to call**. **Start call** stays grey until
   both participants have agreed on their consent form (see section 7, step 3) and the top of
   the page says **Phone line: Ready**.
3. Click **Start call**. The phone system rings participant A. The card shows **On the call**,
   with one button at a time; if the call could not be placed, the card says why.
4. When A answers, click **A answered – call B**: the phone system rings B into the same call. If
   B does not answer, click **Ring B again** (3 times at most in one call).
5. When B answers, click **B answered – start recording**. The recording starts now.
6. Stay on the call, **muted**, and listen. If the line is poor (noise, echo, breaking up), tell
   them, then click **Cancel this call** and choose the **Reason** **Poor line quality**.
7. When they have finished, click **Stop and close call**. The whole call is recorded by the
   phone system; only the part between "B answered" and "Stop" is delivered, checked and counted.
8. The card shows **Fetching the recording**. The platform fetches the call's recording from the
    phone system, usually within a few minutes. The page updates on its own. You can still cancel
    the call while it is being fetched.
9. When it arrives, the task moves to **Recorded**. Click **Listen**; if it is good, **Send to
    QC**; if not, **Call again**.

If the call did not work (no answer, wrong number, dropped), click **Cancel this call** and choose
the **Reason**. You can then start a new call. A task can be called at most 6 times in an hour.

**Needs a person to pick the recording.** If several calls in the phone system fit the time, or
none shows participant A's number, the card lists them with their start time, length and the last
two digits of each number. Click **This is the call** on the right one. If none was found, or the
phone system could not be searched (the card says why), click **Look for the recording again**
later, or cancel the call. A project admin can do the same, and cancel a call, from the task's
**Phone calls** history.

**Phone calls page.** The menu has **Phone calls** (Super Admin, Project Admin, Moderator). A
moderator's page is **My phone calls**: the list of their own calls, newest first, each with a
link to its task. Admins choose a **Project** and a **Period** (7, 30 or 90 days). Their page has
two tabs, **Figures** and **All calls**. Long tables show 10 rows; click **Show all** for the
rest. The **Figures** tab shows:

- Calls; recorded (and the share of calls); failed or cancelled; **needs a person**
  (also calls left open); average call; recorded audio and how long recordings take to arrive;
  **Today** against the project's daily phone call target; phone tasks **not called yet**.
- **Calls per day** (recorded, still open, failed or cancelled), with a table view.
- **From call to approval**: calls started, accepted by TxContact, closed by the moderator,
  recording stored, tasks sent to QC, tasks approved.
- **Phone tasks by status**, **Calls by hour of the day**, **By moderator**, and **By project**
  when you look at all your projects.
- **Automatic audio check** and **QC decisions** on call recordings.
- **Why calls were cancelled** and **Problems getting the recording**.
- Project admins also see **TxContact: calls per hour**, TxContact's own count for the account.

The **All calls** tab lists every call with a link to its task; **Show** filters it (for example
**Needs a person**). **Download calls (CSV)** saves the period's calls as a spreadsheet.

Moderators have no figures, charts or CSV: only the list of their own calls. No page shows a
full phone number: the last two digits only.

**Phone calls history.** Every task shows each call with every step, in plain words: when it was
started, when A and B were rung, each checklist tick, when it was closed, which recording was found
or chosen and when it was stored. The phone system's own answers are in a closed **Technical log**,
for the Super Admin only. The recording's details file (in **Download with consent form** and
in the project's metadata export) carries the same history in its **call** section.

---

## 8. QC Executive: checking a recording

1. Open **Tasks** (set **Status: Audio QC** to see only waiting work), or your **Dashboard**.
2. Open the task. The **Audio quality** card shows the automatic check: overall **Passed**,
   **Listen and decide** or **Failed**. Only the checks that need attention are listed; **Show
   all checks (n)** shows every check (format, length, silence, clipping, loudness, duplicates and
   more).
3. Click **Listen** to hear the recording.
4. Under **Your decision**, click:
   - **Pass** → the task becomes **Admin review** (the admin gives final approval);
   - **Reject** → **Rejected** (final).

   Reject asks for a **Reason** (a **Comment** is needed when the reason is "Other"). Passing a
   recording the automatic check failed asks **Why does it pass?**.

**Check the stored file again** repeats the automatic check on the stored file.

The automatic check never approves or rejects anything by itself; a person always decides.

### Project Admin: final approval

A task that passed QC shows **Admin review**. Open it: the **Final approval** card says **QC passed
this recording. Listen, then approve or reject it.** Click **Listen**, then **Approve**, or
**Reject** (it asks for a **Reason** and a **Comment**). After **Approve** the task is **Approved**
and ready to download.

**Many at once** (Tasks list): tick the tasks (or the box at the top of the list for the whole
page). A bar appears with:

- **Approve selected (N)**: approves the ticked tasks that are waiting for admin review; the others
  are skipped and named.
- **Clear selection**: removes the ticks.

### Export a project

Open the project and click the **Export** tab (Super Admin and Project Admin).

**Recordings** are exported as one ZIP, prepared in the background:

1. Choose **What to export**: **Audio + metadata**, **Audio only** or **Metadata only**.
2. Choose **Which recordings**: **Approved tasks only** (the delivery) or **Every finished
   recording**. You can narrow it by **Recording type** (face-to-face or phone calls), **Language**,
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

Every conversation has two participants, and its length is **split equally** between them: a
5-minute conversation gives each participant **2.5 minutes**. The recorded, approved and payable
minutes shown for a participant are all their share. Payment follows **approved** audio. A re-recorded task counts once (its newest finished recording). Project Admins see the
**Recorded min**, **Approved min** and **Payable min** columns on the project's **Participants**
tab; the **Participant minutes** export gives the same numbers as a spreadsheet.

---

## 9. Client Viewer: progress

The **Dashboard** (**Collection progress**) shows recorded and approved hours, today's hours
against the daily target, and an hours-per-day chart. Choose a **Project** and a **Period** (last 7,
30 or 90 days, or **Choose dates (from – to)**). You can narrow it by **Recording
type**, **Language** (and **Dialect**, when the project has any) and **District**. Days are counted in India
Standard Time.

### Dashboard filters (everyone)

Under the page title is a row of filters. Each one narrows every figure on the page:

| Filter | Who has it | What it does |
|---|---|---|
| **Project**, **Period** | everyone | One project or all of yours; the last 7, 30 or 90 days, or **Choose dates (from – to)** |
| **From**, **To** (with Choose dates) | everyone | Counts only recordings started on those days; the chart shows exactly those days. At most 366 days |
| **Recording type** | everyone | Face-to-face or phone call |
| **Language**, **Dialect** | everyone | Conversations in which a participant speaks it |
| **District** | everyone | Conversations with a participant from that district (shown once participants have a district) |
| **Task status** | staff | Tasks in that status |
| **Staff** | Super Admin, Project Admin | One person's tasks and the recordings they made |

**Clear filters** takes them all off. Without chosen days the totals at the top count
everything ever recorded; with chosen days they count those days only.

Managers also see **Phone calls**: placed, recorded, could not be placed, waiting for a person,
still open. Under **Needs attention**, the **Waiting for audio QC** and **Tasks on hold** tiles open
the **Tasks** list filtered to those tasks.

---

## 10. Participant: the private page

The participant opens the link from the consent email. No login is needed. The page shows:

- **Your details**: code, name, language, dialect and the last two digits of the phone number.
  Read-only; to correct anything the participant contacts the project team.
- **Minutes**: sessions, recorded time, accepted time, and **Your share for payment** (half of
  each accepted conversation).
- **Consent form**: read it, tick **I have read and understood this form**, click **I agree** or
  **I do not agree**. After agreeing the page says **You agreed on <date>.** with no buttons: the
  answer is final. After **I do not agree** they can still agree later.
- **Your sessions**: each session and its state (**Planned**, **Recorded, being checked**,
  **Accepted**, **Not used**).

The link works for 30 days. If it stops working, the project team sends a new one.

---

## 11. Not available in this version

- **Phone calls are new and not yet tested on the TxContact account.** Try one test call (section
  7a) before real work. Whether a second person can be added to a call, and whether the two
  speakers are recorded apart, is for TxContact to confirm.
- **Transcription.**

---

## 12. Problems and fixes

| What you see | What to do |
|---|---|
| "Microphone permission was refused" | Click the lock icon in the address bar, allow the microphone, reload. |
| "No microphone was found" | Connect a microphone, then choose it again. |
| "This browser cannot record here" | Use the latest Chrome or Edge on a computer. |
| "This browser cannot record at 16000 Hz" | Use the latest Chrome or Edge. |
| New task: **Create task** stays grey | Choose both participants. If the lists are empty, the project needs at least two participants: use **Add participants to the project**. |
| New task: a participant is not in the list | Only people who agreed to the consent form can be chosen. If their email was lost, click **Email consent form again** on the Participants page. |
| "Unexpected Application Error" / "Failed to fetch dynamically imported module" | The site was updated while the page was open. The page now reloads by itself; if the message stays, press Ctrl+Shift+R (Cmd+Shift+R on a Mac). |
| "The task must be in progress to record" | Moderator: open the task and click **Start session**. If the task is on hold, ask the Project Admin to click **Resume task**. |
| "This link is invalid or has expired" | Ask for a new link: **Forgot your password?**, or the admin's **Send password link**. |
| "Too many failed sign-in attempts" | Wait 15 minutes, then try again or reset the password. |
| No invitation or consent email | Check spam. Emails come from no-reply@dubdesk.live. For a consent form, click **Email consent form again**. |
| "No access" | Your role does not include that page. Ask an administrator. |
| **Phone line not connected** at the top of the page | Click **Try again**. If it fails again, ask your admin to check your phone seat number and password. |
| The site does not open on one computer only | That computer still remembers an old address. Wait a few hours or restart the router. |
