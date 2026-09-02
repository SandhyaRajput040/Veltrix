# Veltrix

Unattended daily automation that syncs Amazon.in inventory (seller account
**Rising Brothers**) from supplier **Baapstore**'s Google Drive files.

Pipeline (target end state):

```
Baapstore Google Drive -> Download -> Validate -> Quarantine bad rows
  -> Amazon TXT feed -> Submit via SP-API -> Monitor -> Report -> Email me
```

## Status

- [x] Module 1 -- Project scaffolding & configuration loading
- [x] Module 2 -- Google Drive downloader
- [x] Module 3 -- Inventory validation & Amazon TXT conversion
- [x] Module 4 -- Amazon SP-API feed submission
- [x] Module 5 -- Daily scheduler
- [ ] Module 6 -- Logging & email notifications
- [ ] Module 7 -- Deployment

## Project layout

```
Veltrix/
├── src/
│   ├── config/           # settings.py -- loads all configuration from env vars
│   ├── drive/             # Module 2: Google Drive downloader (auth, list, download, state)
│   ├── inventory/          # Module 3: read Template sheet, validate rows, write TXT + quarantine CSV
│   ├── amazon/              # Module 4: SP-API feed submission (auth, client, feed builder, submitter)
│   ├── scheduler/            # Module 5: ties Drive sync -> validation -> submission into one daily run
│   └── notifications/         # (placeholder) Module 6: email notifications
├── tests/                       # automated tests, one file per module
├── data/
│   ├── input/                     # downloaded Baapstore files land here (gitignored)
│   ├── output/                     # generated Amazon TXT feeds (gitignored)
│   └── quarantine/                  # quarantine_report.csv per run (gitignored)
├── state/                              # drive_state.json, amazon_product_type_cache.json (gitignored)
├── ready_to_upload/                      # fallback-mode JSON feed batches, not yet submitted (gitignored)
├── logs/                                   # run_daily.log (gitignored) -- temporary until Module 6
├── main.py                                   # entry point -- runs one full daily pipeline pass
├── run_daily.bat                               # Windows Task Scheduler launcher (see Module 5 below)
├── requirements.txt
├── .env.example                                  # documents every required environment variable
└── .gitignore
```

## Local setup (Windows)

**IMPORTANT: use a real local drive (e.g. `C:\...`), not a virtual/cloud-sync
drive letter.** If your project lives on a drive created by Google Drive for
Desktop, OneDrive, or similar (check by running `C:\Windows\System32\subst.exe`
and `C:\Windows\System32\net.exe use` -- if neither lists your drive letter,
but File Explorer still shows an unusual "Volume label" like "My Drive" when
you run `dir` on it, it's likely a sync-client virtual drive), Windows Task
Scheduler may silently fail to run scripts from it. See the Module 5
troubleshooting section below for the full story.

**PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Then edit `.env` and fill in any values you already have.

## Running

```powershell
python main.py
```

This runs one full pipeline pass: Google Drive sync -> validate & convert ->
submit to Amazon (or fallback, depending on `AMAZON_FALLBACK_MODE`).

Manual smoke tests for individual modules:

```powershell
python -m src.drive.downloader      # Module 2 only: sync files from Google Drive
python -m src.inventory.pipeline    # Module 3 only: validate + convert files in data\input\
python -m src.amazon.submitter      # Module 4 only: submit/fallback-write files in data\output\
```

## Testing

```powershell
python -m pytest tests\ -v
```

Current count: **100 tests**, all passing.

## Environment variables

See `.env.example` for the full list.

| Variable | Used by | Notes |
|---|---|---|
| `APP_NAME`, `ENVIRONMENT`, `DEBUG` | all modules | general app config |
| `GOOGLE_DRIVE_CREDENTIALS_FILE` | Module 2 | path to your service-account JSON key |
| `GOOGLE_DRIVE_FOLDER_ID` | Module 2 | Baapstore's Drive folder ID |
| `AMAZON_LWA_CLIENT_ID`, `AMAZON_LWA_CLIENT_SECRET`, `AMAZON_REFRESH_TOKEN` | Module 4 | Login-with-Amazon credentials (see setup below) |
| `AMAZON_SELLER_ID`, `AMAZON_MARKETPLACE_ID` | Module 4 | your seller account + marketplace |
| `AMAZON_SP_API_ENDPOINT` | Module 4 | defaults to the EU-region endpoint (covers Amazon.in) if left blank |
| `AMAZON_FALLBACK_MODE` | Module 4 | `True` (default/safe) writes to `ready_to_upload/` instead of calling Amazon |
| `BAAPSTORE_*` | (reserved) | not currently used -- Baapstore delivery is via Drive, not an API |
| `NOTIFICATION_EMAIL`, `SMTP_*` | Module 6 | not needed until Module 6 |

## Module 2 -- Google Drive setup

1. Create a Google Cloud project, enable the Google Drive API.
2. Create a service account, download its JSON key, store it outside the repo.
3. Share the Baapstore folder with the service account's email (see the
   access-model note below).
4. Set `GOOGLE_DRIVE_CREDENTIALS_FILE` and `GOOGLE_DRIVE_FOLDER_ID` in `.env`.

**Access model:** a service account is a separate identity from your own
Google account. If Baapstore's folder is shared as "Anyone with the link,"
the service account can access it directly. If it's invite-only, you'll
likely need to ask Baapstore to add the service account's email as a Viewer
-- a plain Viewer typically can't re-share to a new email themselves.

**State tracking:** `state/drive_state.json` remembers each tracked file's
last-downloaded Drive `modifiedTime`, so unchanged files are skipped on
later runs. Delete this file to force a full re-download.

## Module 3 -- Inventory validation rules

Every row from the `Template` sheet is checked against:

- **SKU present** -- blank/missing SKUs are quarantined.
- **SKU byte length** -- Amazon's limit is 40 **bytes**, not characters.
  Multi-byte characters (e.g. Devanagari) count for more than 1 byte each.
- **SKU characters** -- the Unicode replacement character or raw control
  characters are treated as corruption and quarantined.
- **Duplicate SKUs** -- if a SKU appears more than once in the same source
  file, **every** occurrence is quarantined (no occurrence is silently kept
  as "the right one" -- see `src/inventory/validator.py`'s docstring for the
  full policy).
- **Quantity present, whole number, non-negative** -- a whole-number float
  (`10.0`) is cleaned to `10`; a genuinely fractional quantity (`10.5`) is
  quarantined, not rounded.

Rejected rows never reach the Amazon TXT file -- they're written to a
quarantine CSV instead, with the source file, row number, SKU, quantity,
a short reason code, a human-readable explanation, and a timestamp.

## Module 4 -- Amazon SP-API setup

**Important context:** the flat-file inventory feed types originally assumed
for this project (`POST_FLAT_FILE_INVLOADER_DATA` and similar) were
deprecated by Amazon for programmatic Feeds API submission, effective
March 31, 2025. This project uses the modern replacement,
**`JSON_LISTINGS_FEED`** with `PATCH` operations that touch only the
`fulfillment_availability` (quantity) attribute -- never price, title,
images, or anything else. Your existing manual Seller Central upload
process is unaffected by this deprecation and remains a valid fallback
(see below).

**Authentication:** as of Amazon's October 2023 change, SP-API only needs a
Login-with-Amazon (LWA) bearer token -- no AWS IAM credentials or AWS
Signature V4 signing required.

### Setup steps (you do this in Seller Central + Amazon Developer Console)

1. In Seller Central, go to **Settings -> User Permissions** and register as
   a developer if you haven't already.
2. Create a new SP-API application. Since this is for your own single
   seller account (not a public app for other sellers), you can
   **self-authorize** it immediately -- no waiting for Amazon's app review.
3. Follow Seller Central's "Develop apps" flow to authorize the app against
   your Rising Brothers account. This gives you a **refresh token**.
4. From the app's settings, note your **LWA Client ID** and **LWA Client
   Secret**.
5. Set `AMAZON_LWA_CLIENT_ID`, `AMAZON_LWA_CLIENT_SECRET`,
   `AMAZON_REFRESH_TOKEN`, `AMAZON_SELLER_ID`, and `AMAZON_MARKETPLACE_ID`
   in `.env`.
6. Set `AMAZON_FALLBACK_MODE=False` once you're ready to actually submit to
   Amazon instead of writing to `ready_to_upload/`.

### Fallback mode

Until the above is set up (or any time you want a manual safety net),
`AMAZON_FALLBACK_MODE=True` (the default) means the pipeline **never calls
Amazon**. Instead, it writes the exact JSON that would have been submitted
into `ready_to_upload/`, clearly labeled as not-yet-submitted. Your current
manual process (uploading a flat file through Seller Central) still works
independently of this project and remains a valid permanent fallback.

### productType caching

JSON_LISTINGS_FEED PATCH messages require a `productType` per SKU. This is
looked up once per SKU via the Listings Items API and cached locally in
`state/amazon_product_type_cache.json`, so a daily run doesn't re-fetch it
for every SKU every time. Delete this file to force fresh lookups.

## Module 5 -- Daily scheduler (Windows Task Scheduler)

**Why Task Scheduler:** free, built into Windows, and needs no extra service
-- the right choice while this runs on your own PC. Cron doesn't exist
natively on Windows; GitHub Actions or a cloud scheduler make more sense
once this moves to a server (a possible Module 7 direction).

### Setup (use the GUI, not just the command line -- see troubleshooting below)

1. Press `Win + R`, type `taskschd.msc`, press Enter.
2. Click **Create Task...** (not "Create Basic Task").
3. **General tab:** name it `Veltrix Daily Inventory Sync`, select **"Run
   whether user is logged on or not"**, check **"Run with highest
   privileges."**
4. **Triggers tab -> New:** On a schedule, Daily, start time of your choice
   (e.g. 6:00 AM).
5. **Actions tab -> New:** Start a program, browse to your project's
   `run_daily.bat`.
6. Click **OK** on the main dialog -- Windows will prompt for your account
   password. Enter it. This step matters (see troubleshooting below).
7. **Recommended:** right-click the task -> Properties -> **Settings** tab
   -> set "If the task is already running" to **"Do not start a new
   instance"** so overlapping runs can't happen.

### Testing it manually

```powershell
C:\Windows\System32\schtasks.exe /run /tn "Veltrix Daily Inventory Sync"
Get-Content <your-project-path>\logs\run_daily.log
```

### Troubleshooting

- **`schtasks` (or `subst`, `net`) "not recognized"**: your PATH is missing
  `C:\Windows\System32`. Use the full path,
  `C:\Windows\System32\schtasks.exe`, as a workaround, and consider fixing
  your PATH via System Properties -> Environment Variables.
- **Task shows `Last Result: 0` (success) but no log file / nothing
  happened**: your project folder is likely on a virtual drive (Google
  Drive for Desktop, OneDrive, a `subst` drive, or a mapped network drive)
  that's only visible in your interactive login session, not to Task
  Scheduler's separate process context. Check with
  `C:\Windows\System32\subst.exe` and `C:\Windows\System32\net.exe use`; if
  neither lists your drive letter, run `dir <yourdrive>:\` and check the
  "Volume label" -- a label like "My Drive" indicates Google Drive for
  Desktop. **Fix: move the project to a real local drive (e.g.
  `C:\Projects\Veltrix`) and recreate `.venv` and the scheduled task there.**
- **Task shows `Last Result: -2147020576` (hex `0x800710E0`)**: a known
  Windows Task Scheduler quirk, most common when a task was created via the
  `schtasks` command line rather than the GUI. **Fix: delete the task and
  recreate it through the Task Scheduler GUI** (steps above) -- the GUI
  properly prompts for and stores your account credentials, which the CLI
  path sometimes doesn't do reliably.
- **Log file never appears at all**: confirm the batch file's target path
  in the task's Actions tab matches your project's real location exactly,
  and that `run_daily.bat` and `main.py` both exist there.

## Failure handling

`src/scheduler/run_daily_job.py` isolates failures per file: if the Google
Drive sync itself fails (checked first, with retries for transient network
errors), the whole run is marked `FAILURE` with a clear reason and nothing
else is attempted. If Drive sync succeeds but one particular downloaded
file fails validation or Amazon submission, that failure is recorded
against that file only -- other files in the same run still get processed,
and the overall run is marked `PARTIAL_FAILURE` rather than losing visibility
into what succeeded.

## Manual rerun

Since Module 2's state tracking only downloads changed files, simply running
`python main.py` again (or re-triggering the scheduled task) is always safe
-- unchanged files are skipped, and nothing is re-submitted to Amazon that
was already successfully accepted in a prior run for that exact file
version.

## Credential rotation / deployment / troubleshooting (general)

Not fully documented yet -- these will be filled in as Modules 6 and 7 are
built.