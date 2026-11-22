# User guide

Conversation Collection records two-person conversations, face to face, in the web browser. It
keeps each participant's consent, checks the sound quality on its own, and lets a person approve
or reject every recording.

Website: **https://dubdesk.live**. Use a current Google Chrome or Microsoft Edge on a computer.

Words in **bold** are the exact labels you see on screen. In a table, a row's actions are small
icons: point at one to see its name (for example the pencil is **Edit**).

Dates and times are in India time, written the Indian way, for example 17 Nov 2026, 1:57 pm.

---

## 1. Who does what

| Role | What they do | Menu they see |
|---|---|---|
| Super Admin | Everything: users, projects, settings | Dashboard, Projects, Tasks, Phone calls, Participants, Users, Settings, Payments, Audit log, System status |
| Project Admin | Runs projects they belong to: participants, tasks, who records, who checks, downloads, payments | Dashboard, Projects, Tasks, Phone calls, Participants, Payments, Audit log |
| Moderator | Records conversations on tasks given to them | Dashboard, Projects, Tasks, Phone calls |
| QC Executive | Listens to recordings and approves or rejects them | Dashboard, Projects, Tasks |
| Client Viewer | Sees the progress of their projects | Dashboard, Projects |
| Participant | The person being recorded; has no login, uses a private link | (their own private page) |

People only see projects they have been added to. The Super Admin sees every project.

A project has its own menu beside the side menu (Progress, Team, Participants, Tasks, Audio rules,
Rules, Languages, Retention, Export; on a phone, a row of buttons at the top) for the Super Admin
and Project Admin only. Everyone else sees the project's **Overview**.

---

## 2. Signing in

**First time.** The Super Admin adds you. You get an email from **no-reply@dubdesk.live** with the
subject **"You have been invited to Conversation Collection"**. Click the link (it works for 72
hours), type a password twice (12 to 128 characters, not your email) and click **Set password**.
Then sign in at https://dubdesk.live with your email and password.

**Forgot your password.** On the sign-in page click **Forgot your password?**, type your email,
click **Send reset link**. The emailed link works for 30 minutes. At most 3 links per hour.

**Signed out by itself.** After 3 hours without use, and after 12 hours in any case. An open recording or phone call keeps you signed in.
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
| 5 | Audio QC | QC Executive | Answers the QC checklist, then Pass (goes to the admin), Reject, or Send back for consent |
| 6 | Admin review | Project Admin | Listens and gives the final word: **Approve** or **Reject** with a reason |
| 7 | Approved | - | Done; the recording can be downloaded with its consent form |

If a project has **QC pass is the final approval** ticked (the project's **Rules**), step 6 is
skipped: **Pass** at step 5 makes the task **Approved** at once.

In a project whose **Consent** is **Upload**, QC also checks each person's signed consent form.
When the recording is fine but a form is not, QC sends the task back: it shows **Consent form to
fix** until the moderator uploads a new form and sends the same recording back to **Audio QC**
(nothing is recorded again).

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

To see a participant's own page, open the project's **Participants** page and click the eye
(**Their page**) on the row (Super Admin only). It is the page the participant sees, without the
consent buttons.

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

The project's rules (speaker ages and details, pairing, consent, approval) are not on this form:
a new project starts with the usual ones, and you change them under its **Rules** (below).

After **Create project** you return to the project list. A new project starts as **Draft**: click
its code to open it and, on **Overview → Status**, click **Make active**. Only **Active**
projects accept new tasks and recordings, and only they appear in **New task**.

The **Status** card has a button for each next step: **Make active**, **Pause**, **Mark as
completed**, **Archive**, and **Reopen** for a completed or archived project. Each asks you to
confirm; archiving or reopening also needs a reason.

The project's menu:

- **Overview**: the project settings and its status.
- **Progress**: what was collected against the project's targets (below, **Progress**).
- **Rules**: what the project asks of its speakers, how consent is given, who gives the final
  approval, what QC checks, what the moderator fills and reads, long pauses and the targets
  (below). Everyone in the project can read them; only admins change them.
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

### Rules (project admins)

Each client's rules are the project's own: open the project, click **Rules** and then the section
under it (Speakers, Consent, Approval, QC checklist, Device details, Reminders for moderators,
Audio and progress, Targets, Export format), change what you need and click **Save rules** at the
top of the section. Each section is saved on its own. A new project starts with the values below,
and older projects have them too. Every change is saved in the audit log with the project.

- **Speakers**
  - **Youngest speaker age** and **Oldest speaker age** (20 and 60 at the start; any of 1 to
    120, the youngest not above the oldest). Checked when someone is added to the project, when
    their age is changed in it, and when a task is made. Someone already in the project keeps
    their age; if it is outside, they cannot be put on a task here.
  - **Conversations per speaker (at most)**: how many tasks one person may be on in this project.
    It starts at 3. Leave it empty for no limit. Cancelled and rejected tasks do not count.
  - **Each pair of speakers only once**: ticked at the start. Two people who already share a task
    cannot be put on another one together. Untick it to allow it.
  - **Speaker details needed before a task**: a box for each speaker detail, grouped as on the
    participant form. All are ticked at the start. **Add participant** asks for the ticked ones
    (marked *), and a task is made only for people who have them; the others may stay empty.
- **Consent**: choose one of two.
  - **Online (participant agrees on their personal page)**: the platform emails each person the
    consent form when they join, and they agree online (section 5, **Consent**). Every project
    made before this option is Online.
  - **Upload (scanned signed form)**: nothing is emailed. The person signs a paper consent form;
    you scan it and upload it when you add them (section 5, **Signed consent forms**). The
    uploaded form is their consent.
  Switching back to Online keeps the uploaded forms on file, but then people need to agree online.
- **Approval**: **QC pass is the final approval (no admin review)**. Leave it empty to keep the
  admin's final approval. Tick it and a recording the QC Executive passes is **Approved** at
  once. Tasks already waiting in **Admin review** stay there; approve them as usual.
- **QC checklist**: the questions the QC Executive answers **Yes** or **No** for every
  recording (section 8). It starts with the client's 28 questions: 13 about the conversation
  (for example "The conversation is between exactly two speakers"), where **No** fails the
  recording, and 15 about each speaker (for example "Is speech intelligible?"), which are only
  noted. Each question is a block with:
  - **Question**: the words QC reads (at most 200 characters).
  - **Applies to**: **The conversation (answered once)** or **Each speaker (answered for both)**.
  - **The recording fails when the answer is**: **No**, **Yes** or **Never (observation only)**.
  - **Required (answered before Pass)**.
  - The arrows move it up or down; the bin removes it.
  To add one, type its **Key** (lowercase letters, digits and _, like `speech_intelligible`; it
  names the answer in the delivery and cannot be changed later) and the **New question**, then
  click **Add question** (it starts as a conversation question that fails on No; change it in its
  block). **Reset to the client's list** puts the 28 questions back. At most 60 questions. The
  list is saved with **Save rules**; answers already given keep the questions as they read then.
- **Device details**: what the moderator fills for each speaker of every conversation before
  **Send to QC** (sections 7 and 7a). Under **Asked for each speaker**, a box for **Device make**,
  **Device model**, **Bluetooth earphones used (Yes / No)**, **Wired earphones used (Yes / No)**
  and **Loudspeaker on (Yes / No)**. All five are ticked at the start. A recording goes to QC only
  when the ticked ones are filled for both people; untick them all to ask none. The call type
  (Telephonic or Face-to-face) comes from the task.
- **Reminders for moderators**: the short note the moderator reads on the recorder before
  **Start recording** and on the call card before **Start call**.
  - **Ask each speaker to start with their first name and speaker ID** (ticked at the start):
    the note shows "I am <first name> and speaker ID P000123" for each of the task's two people.
  - **Talk about**, **Avoid**, **Face-to-face tips**, **Phone call tips**: one entry per line (at
    most 20 lines, 200 characters each). They start with the client's text: talk about daily
    activities, education, agriculture, food and cooking, travel, shopping, health and fitness in
    general, weather, work and hobbies; avoid politics, religion, obscene talk, hate or killing,
    other sensitive topics and personal information; face-to-face: a quiet place, both stay in
    one place, the recording device between the two speakers no more than 2.5 feet from each
    mouth; phone: a quiet place, the handset near the mouth with the loudspeaker off, no
    ringtones or notification sounds.
  - **Reset to the client's text** puts that text back.
- **Audio and progress**:
  - **Long pause (seconds)** (3 at the start; 1 to 30): a silence inside the conversation longer
    than this is a long pause. The automatic check counts them (**Long pauses**, section 8).
  - **Long pauses need a listen** (not ticked at the start): when ticked, a recording with a long
    pause is marked **Listen and decide**; otherwise the pauses are only shown.
  - **Completed minutes count**: **Effective speech (the time someone speaks)** (at the start) or
    **Full length of the recordings**: what the **Progress** page and the dashboard count as
    completed for approved conversations. Payments always count the full length.
  The longest recording allowed stays on the **Audio rules** page.
- **Targets**: what the **Progress** page compares the project with. An empty box is no target.
  - **Hours completed** (empty at the start), counted as **Completed minutes count** says;
    **Speakers** (500) and **Conversations** (600).
  - **Age bands (percent of speakers)**: a line per band with **From age**, **To age** and
    **Percent**; the client's bands at the start: 20-30 40 %, 30-40 30 %, 40-50 20 %, 50-60
    10 %. A band takes the ages from its first age up to, but not including, its last; the band
    that ends highest also takes its last age (a speaker of 30 is in 30-40, one of 60 in 50-60).
    The percents must add up to 100. **Add age band**, the bin to remove one, **Reset to the
    client's age bands**.
  - **Gender (percent of speakers)**: **Male (%)** and **Female (%)**, 50 and 50 at the start;
    both empty for no gender target.
  - **Face-to-face and phone (percent of approved conversations)**: 50 and 50 at the start.
  - **Districts (by native district)**: a line per district with its **State**. None at the start;
    **Use the client's Konkani districts** fills in North Goa and South Goa (Goa), Uttara
    Kannada, Udupi and Dakshina Kannada (Karnataka), Sindhudurg, Ratnagiri and Raigad
    (Maharashtra). Each listed district is expected to give an equal share of the speakers
    (12.5 % each for 8). **Add district** adds one; the bin removes one.
  The line under a wrong list says what is wrong (for example "The percents add up to 90, not
  100."), and **Save rules** waits until it is right.
- **Export format**: how the project's exports are laid out and named (see **Export a project**).
  - **Layout of an export**: **The client's delivery format** (at the start, for every project)
    or **The platform's own layout** (a folder per kind of recording with each recording's details
    file and consent record, as before).
  - **Speaker IDs**: **Number (P000123 is 123)** (at the start; at least 3 digits, so P000007 is
    007) or **Participant code (P000123)**.
  - **Conversation IDs**: **CON and number (T000045 is CON045)** (at the start) or **Task code
    (T000045)**.
  - **Audio file name**: made of `{a}` and `{b}` (the two speakers' IDs), `{a_pin}` and
    `{b_pin}` (their native PIN codes) and `{conversation}` (the conversation ID), with letters,
    digits, `_` and `-` between them. It starts as the client's
    `{a}_{b}_{a_pin}_{b_pin}_{conversation}`. It must hold `{conversation}`, so every name is
    unique. The line under it shows an example, such as "e.g. 001_002_570001_576101_CON001.wav".
  - **Reset to the client's format** puts all four back.
  Exports already prepared keep the layout they were made in.

Tasks made before a change stay as they are.

### Progress (project admins)

Open the project and click **Progress** (right after **Overview**). Only the people who run the
project see it. It is one screen:

- A strip of four figures at the top, each with a bar to its target: **Completed** (the approved
  conversations' effective speech, or their full length, as the project's **Completed minutes
  count** says, against **Hours completed**), **Approved conversations** (against the target),
  **Speakers** (people with at least one approved conversation, against the target) and
  **Effective speech** (how much of the recorded audio is speech).
- **Balance against the targets**: one table with a section each for **Age bands**,
  **Gender**, **Face-to-face and phone** and **Districts**. For each group: under **Actual** the
  count, the percent and a bar with a tick at the target; under **Target** the target percent and
  the **Variance**: actual minus target, "+4 %" above (green), "−6 %" below (red). Age, gender
  and districts are shares of the speakers with an approved conversation, each counted once, with
  their details as they are now (district: native district); people without that detail are under
  **Not given**. Face-to-face and phone are shares of the approved conversations. The first 10
  districts are shown; **Show all** shows the rest.
- Beside it, **Conversations**: a ring with the tasks by stage (approved; waiting for QC or
  approval; in progress; not started; rejected; cancelled) and a table with each count and share.
- **Completed**: for approved conversations and for those recorded but not yet approved, how many,
  their full length and their effective speech; and how many approved ones are not measured yet.
- **Speakers**: with an approved conversation against the target, registered in the project, and
  how many reached the **Conversations per speaker** limit.
- **How these are counted** (click to open) under the table gives these definitions.

**Effective speech** is the time someone speaks: the recording without its silences (quieter than
−50 dBFS on every channel; on a phone call, speech on either side counts once). Gaps under 0.3 s
between words count as speech, and a click under 0.1 s on its own does not. It is measured by
level, so a loud background noise counts as speech; QC listens for noise. Recordings made before
this measurement are measured in the background shortly after the update; until then they count
as no effective speech and the page says how many.

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

**Participants → Add participant** (opens a window; choose the project first):

- **Name or label** (required).
- **Country code** (choose from the list; India +91 is first) and **Phone number** (optional;
  exactly 10 digits, without the country code).
- **Email address** (required): the consent form is sent there. It cannot be removed; someone
  added before emails were required gets one the next time they are edited.
- **Language** (required; choose from the list. When the project has languages, only those
  are listed).
- **Dialect**, **Internal notes** (optional).
- **Speaker details** (the ones the project needs are marked * and required for someone new;
  a task can only be made for people who have them. Which ones, and the ages, are set on the
  project's **Rules**; at the start, all of them and 20 to 60):
  - **Age** (the project's speaker ages, shown under the box) and **Gender** (**Male** or
    **Female**).
  - Where they live now: **Current state**, **Current district**, **Current PIN code**.
  - Where they were born: **Native state**, **Native district**, **Native PIN code**.
  - **Native language** (type it, for example Konkani).
  - **Education** (**Primary School**, **Secondary School**, **Higher Secondary**, **Diploma**,
    **Bachelor's Degree**, **Master's Degree**, **PhD** or **Other**) and **Medium of education**
    (**English** or **Non-English**).
  - Where the recording takes place: **Recording state**, **Recording district**, **Recording PIN
    code**.

  States are chosen from the list of Indian states and union territories. A PIN code has 6
  digits and does not start with 0. **Add participant** stays grey until every needed detail is
  filled in; a wrong age or PIN code is named under its box.
- **Documents** (PDF, JPEG or PNG, at most 10 MB each):
  - **Signed consent form (scan)**: only in a project whose **Consent** is **Upload**, and
    required there.
  - **Address proof (optional now, needed before delivery)**: in every project. It belongs to the
    person, so it is the same in all their projects.

  A wrong type or a file over 10 MB is named under its box. The files are uploaded right after
  the person is added: the message then says, for example, **P000123 added. Signed consent form
  uploaded.** If an upload fails, the person is still added and their **Documents** window opens
  with what went wrong; upload the file again there.

Each participant gets a code such as `P000123`. The speaker details belong to the person: they are
the same in every project they are in.

To change someone's details, click **Edit** on their row. A window **Edit P000123** opens; change
the details and click **Save changes**. Someone added before speaker details existed can be saved
without them; the window says what the project still needs (**Missing: Age, Gender, ...**).
Their row shows **Details missing** until every detail the project needs is in. An age saved
before that is outside the project's speaker ages is kept; the window says they cannot be put on
a task here.

Who sees the speaker details: Super Admins, Project Admins and the moderator of an open task with
the person, like the name. QC Executives and Client Viewers do not.

**Add existing participant** (on a project's **Participants** page): adds someone who is already
in another of your projects, instead of creating them again. Search by code or name, then click
**Add**. They keep their code, details and consent history. Only people who speak one of the
project's languages, and whose age is within its speaker ages, are listed. To add many at once, tick the boxes (or **Select all shown**)
and click **Add selected**.

**Native district**: the district the participant was born in (it was called **District**
before). The dashboard can be filtered by it.

**Add many**: paste or choose a file whose first line is

```
name,phone,email,language,dialect,district,age,gender,current_state,current_district,current_pincode,native_state,native_pincode,native_language,education,education_medium,recording_state,recording_district,recording_pincode
```

`district` is the native district. Every row needs an email. The speaker details may be left out
or empty, but such a row says **speaker details missing**: add them with **Edit** before making a
task with that person. Write `gender` as `male` or `female`; `education` as `primary`,
`secondary`, `higher_secondary`, `diploma`, `bachelors`, `masters`, `phd` or `other`;
`education_medium` as `english` or `non_english`; states in full (for example `Goa`); PIN codes
as 6 digits. A wrong value, or an age outside the project's speaker ages, fails its row with the
same words as the form.
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
   until they agree. For many at once: tick them, then click **Email consent form again** in the
   bar that appears; people who already agreed are skipped and named.
6. **Consent history** shows earlier answers, in a window.
7. You can make a task only with people who have agreed (see section 6).

### Signed consent forms (projects whose Consent is Upload)

1. Nothing is emailed. The message after adding someone says **This project takes a signed
   consent form uploaded by staff: no consent form is emailed. Upload it with Documents.**, unless
   you uploaded the form with **Add participant**.
2. The uploaded form is their consent: the **Consent form** column shows **Form uploaded**, and
   you can make tasks with them. Someone who already agreed online (for example before the
   project was switched to Upload) still counts.
3. Without either, the row shows **Consent form missing**, and no task can be made with them.
4. **Email consent form again** is not offered in these projects.

### Documents

Every row has **Documents** (the page icon). The window shows one table (**Document**, **File**,
**Uploaded**, and the actions as icons):

- **Signed consent form** (this project's) and **Address proof**, each with **Uploaded**, or
  **Consent form missing** / **Address proof missing**; the file name, when and by whom it was
  uploaded, and its size.
- The eye icon (**View**) opens the file in a new browser tab. The link works for a few minutes
  only; click it again later.
- The upload icon: **Upload signed consent form** / **Replace signed consent form** and **Upload
  address proof** / **Replace address proof** (the words show when you point at it). A new file
  takes the place of the current one; the old one is kept.
- **Earlier versions**: a second table of the files that were replaced, with who uploaded and
  who replaced them, and when; each has the eye icon.

The rows also show **Consent form missing** (Upload projects) and **Address proof missing**, so
you can see at a glance who still needs one. The participant's **View** window has the same
**Documents** block. Every upload, replacement and **View** is saved in the audit log.

Removing a participant deletes their address proofs. Their signed consent forms are kept, as the
record of their consent for what was recorded.

### Everything about one participant

Click **View** on a participant's row. One window shows all the platform holds about them in the
project, as small tables in two columns (one column on a phone): **Profile** on the left; **Work
in this project**, **Personal link**, **Consent form** and **Documents** on the right; the
**Sessions** table under both. Admins open the same window from a task page (**Speaker details**
→ **View** in the **Participants** table).

- **Profile**: code, name, phone, email, language, the speaker details (**Speaker details**
  says **Complete** or what is missing; **Age**, **Gender**, **Lives in**, **Native place**,
  **Native language**, **Education**, **Recorded in**), notes, who added them and when, when they
  were last changed, and the projects they are in. **Details missing** at the top means a task
  cannot be made with them yet.
- **Work in this project**: sessions, recorded and approved conversations and minutes, payable
  minutes, phone calls made to them, calls with a recording, and the last call.
- **Personal link**: whether it works, who made it and when, until when it works, when it was
  last opened, and whether it was emailed or passed on by staff.
- **Consent form**: the answer, when, the form version and earlier answers; click **Form text
  they answered** to read the text. **Download consent form** saves it.
- **Sessions**: every task they were part of, with their role (A or B), the other participant,
  the moderator, the status, the recording length, and the number of phone calls. Click the task
  code to open the task.

Nobody on the staff sees a participant's personal link: it is only in the email the participant
gets, so only they can answer the consent form. If the email is lost, use **Email consent form
again**; it sends a new link (the old one stops working), at most once every 10 minutes for the
same person.

### Other actions on ticked rows

- **Also add them to another project**: choose the other project and click **Add to that project**. They stay in this project too, with the same code and consent history. Each one is emailed the other project's consent form; the list under the buttons says what happened to each.
- **Remove**: deletes the person's name, phone, email, notes and speaker details everywhere.
  Not possible while they are on an open task.

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

The project's rules (its **Rules**, section 4) also apply. Someone who cannot be chosen is
greyed out in the list, with the reason after their name:

- **details missing**: they lack a speaker detail this project needs. Add it with **Edit** on the
  Participants page.
- **outside the ages 20 to 60**: their age is outside the project's speaker ages.
- **3 conversations already**: they reached **Conversations per speaker (at most)**. Cancelled and
  rejected tasks do not count.
- **already paired with the chosen A** (in the **Participant B** list): these two already share a
  task and the project has **Each pair of speakers only once**. Choosing another A clears a B who
  cannot be paired with them.

The server checks the same rules when you click **Create task** and says why if it refuses.

**Add many tasks** (on the same page, after choosing the project): paste or choose a CSV file, one
task per line. The first line must be exactly:

```
participant_a,participant_b,mode,priority,due_date,moderator
```

Write participants by their code (`P000001`); both must have agreed to the consent form, or
the row says who has not. The pairing rules apply to each row too, counting the rows above it: a
row says when someone lacks speaker details, is outside the speaker ages, has reached the most conversations, or is
already paired with the other person (in the project or higher up in the file). `mode` is `face_to_face` or `telephony` (a phone
call; empty means face-to-face), `priority` is `low`, `normal`, `high` or `urgent` (empty means
normal), `due_date` is `YYYY-MM-DD`, and `moderator` is the moderator's email (the task is then assigned at once; empty
leaves it in Draft). **Download sample CSV** gives a file with the right first line and two example
rows to fill in. Click **Check rows**, then **Add N tasks**. Up to 500 rows.

The task page is laid out so the status, both people and your next step show without
scrolling. Under the title, a small row of steps shows where the task is (Draft, Assigned, In
progress, Recorded, Audio QC, Admin review, Approved). On the left is your work: the box with
your next step and its button (or, when there is nothing for you to do, one line saying who acts
next, for example "Waiting for QC: Ravi checks the recording."), then the task's records (Audio
quality, Device details, Recordings, Phone calls). On the right, staying in view as you scroll:

- **Summary**: status, recording type, priority, moderator, QC Executive and dates.
- **Participants**: one table with a column for **Participant A** and one for **Participant B**
  and a row each for **Code**, **Name**, **Consent**, **Consent form** (Upload projects: the file
  opens when you click its name; the upload icon uploads or replaces it), **Device details**
  (**Filled** or **Missing**) and, for admins, **Speaker details** → **View** (everything about
  the person, in a window).
- **History**: the newest three entries first; **Show all** lists the rest. Add a comment with
  **Add comment**.

On a phone everything is in one column, your work first.

- **Assign moderator**: on a task with nobody assigned, choose the Moderator and click
  **Assign**. The task becomes **Assigned**. This is refused while one of the two has not agreed
  to the consent form. To change the moderator later, open **Reassign moderator** under the
  **Summary** and give a reason.
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
- **History**: everything that happened (the newest first); add a comment with **Add comment**.

### Downloads

On an approved task, in **Recordings**, click **Download with consent form**. You get three files:

1. The audio file (16 kHz WAV, ready for delivery).
2. The consent record (`consent_<task>_<recording>.html`): both participants' consent for this
   session and their own form answers, plus the audio file's checksum.
3. The details file (`metadata_<task>_<recording>.json`): the project, session, participants,
   device, every file with its measurements, the automatic check and the QC decision.

Downloads are available to the Super Admin and Project Admin.

**Download task files** (top of **Recordings**, on an approved task): one ZIP with the task's
audio, consent record and details file, in the same folders and with the same tables as the
project's **Export**. Only for approved tasks.

**Recorded again.** When the moderator listened and clicked **Record again** (or **Call again**),
the older recording stays in the list, greyed, with the tag **Rejected by moderator – recorded
again**. Only the newest recording is checked by QC, exported and counted in minutes and
payments. QC Executives see only the newest one.

---

## 7. Moderator: recording

1. Open **Tasks** and click your task.
2. Click **Start session** (the highlighted box near the top).
3. Consent is taken automatically from each participant's own consent form: you do not tick it.
   A task is only made for two people who agreed, so you normally see **Agreed** for both. On an
   older task where someone has not agreed, a **Waiting for consent** card lists them; people who
   manage participants can click **Email consent form again** there. A moderator asks their
   admin. **Open the recorder stays grey until both participants have agreed.**

   In a project whose **Consent** is **Upload**, each person shows **Form uploaded** or
   **Consent form missing**. The **Consent form** row of the **Participants** table (right of
   the page) has both forms: click a file's name to open it, and as the task's moderator use the
   upload icon to upload a missing form or replace one (for example with a clearer scan) while
   the task is open. You cannot see their address proof.
4. Click **Open the recorder** (in the same highlighted box). The recorder shows the steps
   **Microphone**, **Sound check**, **Record**, **Save**, **Done**; **Back to the task** is above
   them. It records at 16000 Hz (the project's rate).
5. Click **Allow microphone** and allow it in the browser. Choose the **Microphone** if you have
   more than one, and watch the **Input level**.
6. Optional: **Test (5 s, then play back)** to hear yourself.
7. Read the **Reminders** note near the top to the speakers: each starts with "I am <first name>
   and speaker ID P000123" (their own code is in the note), what to talk about and avoid, and the
   tips (for example: place the recording device between the two speakers, no more than 2.5 feet
   from each mouth, and do not move it). The project sets these under its **Rules**.
8. Click **Start recording**. Talk. Keep the tab open and the computer awake. The audio uploads in
   small parts while you record.
9. Click **Stop and save**. Wait for **Recording saved**.
10. On the same screen, fill the **Device details** table: a row for each detail, a column for
    **Participant A** and one for **Participant B**. Type **Device make** and **Device model**
    (for example Samsung, Galaxy A14) and click **Yes** or **No** for **Bluetooth earphones
    used**, **Wired earphones used** and **Loudspeaker on** (only what the project asks). If a
    person was recorded before in this project, **Same as last time (T000012)** at the top of
    their column fills their last answers in; check them, then click **Save device details**.
    The **Still to fill** row says how many details each person still needs (point at it to see
    which).
11. Click **Listen**. If it is good, click **Send to QC**; if not, click **Record again** and
    record it once more. (The same buttons, and the **Device details** card, are also on the task
    page.) **Send to QC** stays grey ("Fill in the device details of P000123 first") until both
    people's details are saved. After **Send to QC** the task page says **Sent to QC. A QC
    Executive checks it next.**

The platform checks the sound within about a minute of saving; **Send to QC** works once that
check is done. Once the task is with QC the device details are read only (QC and admins see them,
with who filled them in and when).

**Consent form to fix.** In a project whose **Consent** is **Upload**, QC may find the recording
fine but a signed consent form not (for example not signed, or someone else's form). The task
then shows **Consent form to fix**, and its page has a **Consent form to fix** card: whose form,
**What QC found** (QC's words, who and when) and **New form needed** beside each person.

1. Get a new signed form from the person and scan it.
2. Click **Upload a new consent form of P000123** in the card and choose the scan. The person now
   shows **New form uploaded**.
3. Click **Send back to QC**. It stays grey (**Upload the new form first.**) until every form QC
   asked for is replaced. The task goes back to **Audio QC** with the same recording and the same
   QC Executive; nothing is recorded again. The page says **Sent back to QC with the same
   recording.**

A project admin can do the same, or **Cancel task** if no form can be had.

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

The line goes offline when you sign out, when you are signed out after 3 hours without use,
and when you close the tab. Opening the portal again connects it again. No seat password saved
yet? The call card says **Ask your admin to save your phone seat password.**

1. Open **Tasks** and click your **Phone call** task.
2. Click **Start session**. The card says **Ready to call**. **Start call** stays grey until
   both participants have agreed on their consent form (see section 7, step 3) and the top of
   the page says **Phone line: Ready**. The card's **Reminders** note (also shown during the
   call) has what to tell the speakers: each starts with "I am <first name> and speaker ID
   P000123", what to talk about and avoid, and the phone tips (handset near the mouth,
   loudspeaker off, no ringtones or notifications).
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
9. When it arrives, the task moves to **Recorded**. Fill the **Device details** card under the
    call card for both speakers (their phones: make, model, earphones, loudspeaker; see section 7,
    step 10) and click **Save device details**. Click **Listen**; if it is good, **Send to QC**
    (grey until the device details are saved); if not, **Call again**.

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
rest. The **Figures** tab is one dashboard:

- A strip of eight figures: calls; recorded (and the share of calls); failed or cancelled;
  **needs a person** (also calls left open); average call; recorded audio and how long recordings
  take to arrive; **Today** against the project's daily phone call target, with a bar; phone tasks
  **not called yet**.
- **Calls per day** (recorded, still open, failed or cancelled), with a table view, beside **From
  call to approval**: a table of calls started, accepted by TxContact, closed by the moderator,
  recording stored, tasks sent to QC and tasks approved, each with its share of the calls started.
- **By moderator**, beside **Phone tasks by status** (a ring by stage with its table).
- **Checks, decisions and reasons**: two tables with a section each for the **Automatic audio
  check** and the **QC decisions** on call recordings, **Why calls were cancelled** and
  **Problems getting the recording**, each reason with its count.
- **Calls by hour of the day**, and for project admins **TxContact: calls per hour**,
  TxContact's own count for the account.
- **By project** when you look at all your projects.

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
   more). **Long pauses** says how many silences inside the conversation are longer than the
   project's limit and the longest ("3 over 3 s, longest 7.2 s"), with the effective speech
   under it; it asks for a listen only where the project's rules say so. The **Recordings** card
   shows the same under each recording's length: "Effective speech 6 min 12 s · 3 pauses over
   3 s".
3. Click **Listen** to hear the recording. The **Device details** card shows what the moderator
   filled for each speaker (device, earphones, loudspeaker), read only.
4. Under **QC checklist**, click **Yes** or **No** for every question. **The conversation** is a
   table with one row per question. **Each speaker** is a table with one row per question and a
   column for **Participant A** and one for **Participant B** (code and name), so each question
   is answered twice on the same line. You can also use the keyboard: Tab to a question, Space
   to choose, the arrow keys to switch between Yes and No. An answer that fails the recording
   turns red with a cross. The line above the tables counts what is done, for example
   **Answered 31 / 43 · 2 failing**, with a bar. Questions marked **(optional)** may be left. Your
   answers are saved as you tick (**Answers saved.**), so a reload keeps them; they go with your
   decision.
5. **Consent**:
   - In a project whose **Consent** is **Upload**, **Signed consent forms** is one more row with
     a column per person: click **View** to open each form, check it is signed, by the right
     person, for this project, and click **Yes** or **No** (**Consent form of P000123 checked**).
   - In an **Online** project the table shows each person's online answer and its date. The
     platform recorded it: there is nothing to check.
6. **Your decision** stays at the bottom of the screen while you work down the questions. Its
   line says what your answers allow, and why **Pass** is grey when it is (for example **3
   questions still to answer.**). Click:
   - **Pass** → the task becomes **Admin review** (the admin gives final approval). In a project
     where **QC pass is the final approval**, Pass makes it **Approved** at once; the card then
     says **Pass approves the task: this project has no admin review.** Pass works only when
     every required question is answered, no answer fails and (Upload projects) both consent
     forms are **Yes**.
   - **Reject** → **Rejected** (final). Possible at any time; your answers so far are kept.
   - **Send back for consent** (Upload projects) → **Consent form to fix**: the recording is
     fine but a form is not. It works when every required question is answered, none fails and
     at least one consent form is **No**. It asks **What is wrong with the form**; the moderator
     reads it, uploads a new form and sends the same recording back to you. The task then waits
     in **Audio QC** again with your earlier answers filled in: check the new form and decide.

   Reject asks for a **Reason** (a **Comment** is needed when the reason is "Other"). Passing a
   recording the automatic check failed asks **Why does it pass?**.

Everyone who sees the task (the admin at **Admin review** too) finds the newest decision's
answers under **QC checklist**: what was decided, by whom and when; **Show every answer** shows
the same tables, each answer with a tick (it lets the recording pass) or a red cross and
**Fails**.

**Check the stored file again** repeats the automatic check on the stored file.

In a project whose **Consent** is **Upload**, the **Consent form** row of the **Participants**
table on the task also opens both participants' signed forms (click the file's name). You cannot
upload or replace them.

You see only the newest recording of a task. Older ones the moderator replaced with **Record
again** are not shown to you.

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

Open the project and click **Export** in its menu (Super Admin and Project Admin).

**Recordings** are exported as one ZIP, prepared in the background. Under **Recordings** the page
says which layout the ZIP takes: **the client's delivery format** (every project starts with it)
or **the platform's own layout**, with an example audio file name and a link to change it under
**Rules** (section **Export format**).

1. Choose **What to export**: **Audio + metadata**, **Audio only** or **Metadata only**.
2. Choose **Which recordings**: **Approved tasks only** (the delivery) or **Every finished
   recording**. You can narrow it by **Recording type** (face-to-face or phone calls), **Language**,
   and the days it was recorded (**Recorded from**, **Recorded to**; days in India time).
3. Choose **Tables as** CSV or TSV.
4. Optional: **Also include the original recordings** (as recorded, before any processing; much
   larger). Super Admin only: **Also include names, phone numbers and email addresses**. Without
   it, participants appear by code only.
5. The page shows how many recordings fit and how much audio, and in the client's format how
   many values and files are not on file ("3 items missing", or "Nothing missing"). Click
   **Prepare export**. A missing piece never stops the export; the list is in `MISSING.csv`.
6. The export appears under **Prepared exports**: **Waiting**, **Being prepared**, then **Ready**.
   The page checks by itself; you can leave it and come back.
7. Click **Download**. The link works for 5 minutes; click again for a new one. A prepared
   export is kept for 24 hours, then removed. **Remove** takes it away sooner.

If an export shows **Failed**, the reason is written under its name. Prepare it again; if it
fails again, tell the Super Admin. A prepared export in the client's format also shows how many
items it is missing, under the number of recordings.

**What is in the ZIP in the client's delivery format** (the example: speakers P000001 and
P000002 with native PIN codes 570001 and 576101, tasks T000001 by phone and T000002 face to face):

| Folder or file | What it is |
|---|---|
| `face_to_face/audio/`, `telephonic/audio/` | The 16 kHz WAV of each recording, named as the **Audio file name** says: `001_002_570001_576101_CON002.wav`. `originals/` beside it, if asked for |
| `face_to_face/metadata/`, `telephonic/metadata/` | One file per speaker of each conversation, `001_CON002_570001_METADATA.json`: speaker ID, device make and model, call type (Telephonic or Face-to-face), Bluetooth earphones, wired earphones, loudspeaker (Yes or No), then that speaker's QC answers (Yes or No) under the checklist keys, from the newest QC decision |
| `speakers/` | Once per speaker: `001_570001_METADATA.json` (age, gender, where they live, native state, district, language and PIN code, education and its medium, where they were recorded), `001_consent.pdf` (the signed consent form as uploaded; a scan uploaded as a photo stays `.jpg` or `.png`; in an Online project, or without a signed form, the speaker's online consent record, `001_consent.html`), `001_speaker_proof.pdf` (the address proof as uploaded) |
| `SPEAKER_METADATA_README.json` | What each key of the metadata files means |
| `MISSING.csv` | Everything not on file, a line each: speaker ID, participant code, conversation ID, task code, what is missing and why (for example "No address proof uploaded", "Not filled" for device details, "No QC decision with checklist answers yet") |
| `recordings.csv` or `.tsv`, `recordings.json` | One row per recording, with its conversation ID, both speaker IDs and their files |
| `participants.csv` or `.tsv` | The speakers, by code and speaker ID, with their files |
| `manifest.json`, `manifest.csv`, `SHA256SUMS`, `schema/`, `README.txt` | As below |

**Audio only** holds the audio folders and the tables; **Metadata only** has no audio. In the
JSON files a value not on file is empty (`""`), and a native PIN code not on file is `000000` in
file names; both are listed in `MISSING.csv`. The client's files hold no names, phone numbers or
email addresses. They do hold the speakers' age, gender and PIN codes, so only the project's
admins prepare and download an export in this format (a Client Viewer cannot).

**What is in the ZIP in the platform's own layout:**

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
page; the **Participant minutes** export gives the same numbers as a spreadsheet.

### Payments (Super Admin and Project Admin)

Menu **Payments**. It shows what each person earned on **approved** tasks.

**Rates.** At the bottom of the page, each project has two rates in rupees per approved minute:
**Moderators** and **Participants**. Click **Change**, type the rates (for example `2.50`) and
click **Save rates**. Leave a box empty when there is no rate yet. Every change is kept in the
**Audit log**. A new rate also changes the amounts for work approved before.

**Filters.** Choose a **Project** (or **All my projects**) and the days the tasks were approved:
**Approved from** and **Approved to** (India time).

**Two tabs:**

- **Moderators**: one row per moderator and project: **Approved tasks**, **Approved minutes**
  (the full length of the tasks they recorded), **Rate** and **Amount**. **Search by name**.
- **Participants**: one row per participant and project: **Code**, **Name**, **Approved
  sessions**, **Payable minutes** (their half of each session), **Rate** and **Amount**.
  **Search by code or name**.

Only approved tasks count. A task recorded again counts once, with its newest recording.
With **All my projects** a person who worked on two projects has two rows, one per project,
because each project has its own rate. The **Total** line adds them up. A project with no rate
shows the minutes and **No rate set** instead of an amount; the Total line says how many
minutes have no rate.

**Download CSV** saves the tab as a spreadsheet with the same rows and a **Total** line.

Moderators, QC Executives and Client Viewers do not see payments.

---

## 9. Client Viewer: progress

The **Dashboard** (**Collection progress**) shows recorded and approved hours, the effective
speech in them, **Completed** hours (approved, counted as each project's rules say: effective
speech or the full length; several projects add up their own), today's hours against the daily
target, and an hours-per-day chart. Choose a **Project** and a **Period** (last 7,
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
| **District** | everyone | Conversations with a participant whose native district it is (shown once participants have one) |
| **Task status** | staff | Tasks in that status |
| **Staff** | Super Admin, Project Admin | One person's tasks and the recordings they made |

**Clear filters** takes them all off. Without chosen days the totals at the top count
everything ever recorded; with chosen days they count those days only.

The page is one screen: a strip of key figures (recorded, approved and completed hours with a
small trend line, today against the daily target and approved tasks, each with a bar), then
**Hours per day** beside **By recording type** (one table: face-to-face, phone and the total, for
recordings, recorded, effective speech, approved, completed and the daily target). Staff also see
**Tasks by status** (a ring by stage, each stage's statuses named under it, with a table of
counts and shares) and **Audio QC** (the QC decisions, and the automatic check of the recordings
waiting, as two bars with their counts).

Managers also see **Needs attention**, **Moderator output** (10 rows; **Show all** for the rest),
**Phone calls** (placed, recorded, could not be placed, waiting for a person, still open) and
**Storage used**. In **Needs attention**, a queue with work in it has its count in amber; the
**Waiting for audio QC**, **Tasks on hold** and **Consent forms to fix** (sent back by QC for a
new signed form) rows open the **Tasks** list filtered to those tasks.

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
| New task: a participant is not in the list | Only people who agreed to the consent form can be chosen. If their email was lost, click **Email consent form again** on the Participants page. In an Upload project, upload their signed consent form with **Documents**. |
| An upload says "Only PDF, JPEG or PNG files can be uploaded" or "larger than 10 MB" | Scan the page again as a PDF or a photo (JPEG or PNG), at a lower resolution if it is large. |
| New task: a participant is greyed out | The reason is after their name: **details missing** (add them with **Edit**), **3 conversations already**, or **already paired with the chosen A**. See section 6. |
| "Unexpected Application Error" / "Failed to fetch dynamically imported module" | The site was updated while the page was open. The page now reloads by itself; if the message stays, press Ctrl+Shift+R (Cmd+Shift+R on a Mac). |
| "The task must be in progress to record" | Moderator: open the task and click **Start session**. If the task is on hold, ask the Project Admin to click **Resume task**. |
| **Send to QC** is grey: "Fill in the device details of P000123 first" | Moderator: fill the **Device details** card for both speakers (only the boxes shown) and click **Save device details**. After **Send to QC** they cannot be changed. |
| "This link is invalid or has expired" | Ask for a new link: **Forgot your password?**, or the admin's **Send password link**. |
| "Too many failed sign-in attempts" | Wait 15 minutes, then try again or reset the password. |
| No invitation or consent email | Check spam. Emails come from no-reply@dubdesk.live. For a consent form, click **Email consent form again**. |
| "No access" | Your role does not include that page. Ask an administrator. |
| **Phone line not connected** at the top of the page | Click **Try again**. If it fails again, ask your admin to check your phone seat number and password. |
| The site does not open on one computer only | That computer still remembers an old address. Wait a few hours or restart the router. |
