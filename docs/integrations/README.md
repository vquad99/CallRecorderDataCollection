# Integrations evidence

One folder per external provider or model (e.g. `docs/integrations/<provider>/`). For every capability
the platform relies on, record (runbook A1.13, GEN-005):

| Field | Example |
|---|---|
| Feature | Dual-channel conference recording |
| Official documentation URL | https://... |
| Access date | YYYY-MM-DD |
| What the page says (short quote or summary) | ... |
| Written provider answer, if any (date, sender role, no personal data) | ... |
| Test evidence path | docs/evidence/phase5/... |
| Result | VERIFIED / NOT VERIFIED / FAILED |

Never store credentials, API keys or real participant data here.

Current contents: `exotel/` (desk research, D-070), `kathbath/`, and `txcontact/` (the telephony
provider in use, D-101; built from its API description, not yet tested on the account).
