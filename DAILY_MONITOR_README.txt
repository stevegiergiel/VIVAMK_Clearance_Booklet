VIVAMK DAILY CATALOGUE MONITOR
================================

WHAT IT DOES
------------
Every run checks:
  Christmas
  Mega Sale
  Pets
  Personalised
  Winter Warmers

A product counts as printable/available only when the current site scan can obtain
a usable product image. The monitor compares today's printable products with the
last successful run.

If no items disappeared:
  - Nothing is rebuilt.
  - A heartbeat email is still sent:
    "Daily catalogue check OK - no changes"

If one or more items disappeared:
  - The disappearance is checked a second time.
  - Only the affected booklet(s) are regenerated.
  - Only the affected iframe page(s) are regenerated.
  - Changed site pages are committed and pushed.
  - GitHub Pages deployment is triggered by the updated workflow.
  - The email identifies the catalogue, SKU/product removed and says which
    catalogue needs reprinting.

SAFETY
------
The script does not blindly interpret a broken website/network connection as stock-out.
It verifies removals twice. It also refuses to rebuild if a catalogue suddenly collapses
below 50% of its previous product count; this produces an ATTENTION REQUIRED heartbeat.

FIRST RUN
---------
The first successful run establishes the baseline inventory and sends a heartbeat.
It deliberately does NOT ask you to reprint everything.

EMAIL SETUP
-----------
The monitor now reads email settings directly from:
  email_config.ini

The supplied email_config.ini has been included in this package unchanged.

The monitor uses:
  [Email] sender_email
  [Email] app_password
  [Settings] smtp_server
  [Settings] smtp_port

If smtp_user, smtp_password, or to_email are still left as template placeholders,
the monitor automatically falls back to sender_email/app_password and sends the
heartbeat to the sender address.

Do not commit email_config.ini to a public GitHub repository because it contains
mail credentials. Keep it local only.

TEST EMAIL FIRST
----------------
After filling in the SMTP details, run:
  .\test_monitor_email.bat

TEST FULL MONITOR BEFORE SCHEDULING
-----------------------------------
Open PowerShell in the repo and run:
  .\run_daily_catalogue_check.bat

The first run should create:
  monitor_state\
  monitor_logs\

and send a baseline heartbeat email.

WINDOWS DAILY SCHEDULE
----------------------
Run:
  install_daily_task_9am.bat

This creates a Windows Scheduled Task for 09:00 every day.
The PC must be on (or configure Task Scheduler to wake/run when next available).

GITHUB PAGES
------------
The package updates .github/workflows/deploy-pages.yml so that:
  - manual Run workflow still works
  - pushes affecting site/config/generator files automatically redeploy Pages

The daily monitor commits/pushes site HTML only when a confirmed stock removal
actually changes an iframe page.

IMPORTANT
---------
Booklet PDFs are rebuilt locally in output\<sale>\.
The heartbeat email tells you exactly which catalogue needs reprinting.

V2.08 SOLD OUT RETENTION
------------------------
Confirmed disappearances are no longer immediately deleted.

Product states:
  ACTIVE
    Found live with a usable image. A persistent image copy is retained locally.

  SOLD OUT
    Previously ACTIVE, then absent on both verification scans.
    The booklet keeps the cached image and overlays a red diagonal SOLD OUT ribbon.
    The iframe keeps the card, visually dims the image and replaces BUY ME with SOLD OUT.

  BACK IN STOCK
    A SOLD OUT product reappears. It automatically returns to ACTIVE and the normal
    purchase button is restored.

  REMOVED
    A product that remains SOLD OUT for 14 days is removed on the next successful
    daily run. Change daily_monitor_config.json -> safety -> sold_out_retention_days
    if a different period is wanted.

The monitor stores persistent known-good images under:
  monitor_cache/<sale>/

monitor_cache is local runtime data and is excluded from Git.

UPGRADE NOTE
------------
The first v2.08 daily run detects older v2.06 monitor state automatically.
It performs a one-time state upgrade, caching full images/details for future
SOLD OUT cards. That migration does NOT request a reprint by itself.

CHRISTMAS LIVE-CATEGORY AUDIT
-----------------------------
Christmas still uses its PDF as the operational source in v2.08.

To compare that source with the live Christmas category, run:
  run_christmas_live_audit.bat

The audit writes:
  output/christmas/live_audit/christmas_pdf_vs_live_category.csv
  output/christmas/live_audit/christmas_pdf_vs_live_category_summary.txt

Statuses include:
  IN_BOTH_USABLE
  IN_BOTH_NO_USABLE_IMAGE
  PDF_ONLY
  LIVE_ONLY

The audit does not alter christmas.json or the generated Christmas booklet.
Once repeated audits show the live Christmas category is complete and reliable,
Christmas can be switched to category mode and the separate operational PDF/list
can be retired.

V2.10 CORRECTED SYSTEM TASK INSTALLER
-------------------------------------
The earlier v2.09 PowerShell task installer could register a task that caused
Task Scheduler/CIM error 0x80041318 when Get-ScheduledTask parsed its XML.

Do NOT use the v2.09 installer.

Use:
  install_daily_task_SYSTEM_XML.bat

Right-click it and choose:
  Run as administrator

The installer:
  - deletes/replaces VivaMK Daily Catalogue Check
  - writes a Task Scheduler XML definition explicitly
  - registers it using schtasks /Create /XML
  - verifies it using schtasks /Query
  - runs as NT AUTHORITY\SYSTEM
  - requires no Windows password or PIN
  - runs daily at 09:00
  - wakes from sleep/hibernate
  - catches up after a missed start
  - retries every 15 minutes up to 3 times
  - prevents overlapping scans
  - allows up to 4 hours per scan

Its regular schedule begins tomorrow at 09:00 to prevent the installation
itself being interpreted as a missed 09:00 run.

After installing, run:
  test_system_task.bat

This starts the task immediately under SYSTEM. Wait for the normal heartbeat
email before considering the unattended catalogue scan verified.

The project folder remains:
  F:\VIVAMK_Clearance_Booklet

F: must be present as that drive letter when the scheduled task starts.

Git authentication remains a separate verification: credentials available to
your normal Windows account may not automatically be available to SYSTEM.

V2.11 INSTALLER CLEANUP FIX
---------------------------
v2.10 could stop before registration if there was no existing scheduled task.
`schtasks /Delete` reports "The system cannot find the file specified" when the
task is absent; strict PowerShell error handling treated that harmless condition
as fatal.

v2.11 queries first:
  - if the task exists, it is removed
  - if the task does not exist, installation simply continues

Use:
  install_daily_task_SYSTEM_XML.bat

Run it as Administrator.

V2.12 DIRECT CREATE FIX
-----------------------
v2.11 still allowed PowerShell to convert `schtasks /Query` stderr into a
NativeCommandError before the script could inspect the exit code.

v2.12 removes the pre-query/pre-delete step entirely.

`schtasks /Create /F` already creates or replaces the task, so there is no
need to test whether it exists first.

Both task creation and verification now run through cmd.exe with stderr merged
into ordinary output, preventing harmless schtasks messages from becoming
PowerShell terminating errors.

Use:
  install_daily_task_SYSTEM_XML.bat

Run as Administrator.

V2.13 WINDOWS 10 SYSTEM XML FIX
-------------------------------
v2.12 correctly exposed the remaining XML issue:

  LogonType: ServiceAccount

`ServiceAccount` is an API enumeration value, not a valid literal value for
the Task Scheduler XML <LogonType> element on this Windows 10 setup.

For the built-in SYSTEM account, v2.13 uses:

  <UserId>S-1-5-18</UserId>
  <RunLevel>HighestAvailable</RunLevel>

and omits the invalid LogonType element entirely.

All resilience settings remain unchanged:
  - 09:00 daily
  - wake from sleep/hibernate
  - run after missed start
  - retry every 15 minutes, 3 times
  - 4-hour execution limit
  - no overlapping runs
  - SYSTEM account, no password/PIN required

Use:
  install_daily_task_SYSTEM_XML.bat

Run as Administrator.

V2.15 DAILY CHRISTMAS PDF-vs-LIVE AUDIT
---------------------------------------
The normal 09:00 daily monitor now also runs the Christmas comparison
automatically after the stock/SOLD OUT checks.

This audit remains OBSERVATIONAL ONLY. Christmas generation still uses the PDF.

Every heartbeat email now includes:
  - PDF source item count
  - live Christmas category item count
  - common usable item count
  - PDF-only count
  - live-only count
  - price mismatch count
  - image failure count
  - whether the audit changed since the previous successful audit
  - consecutive stable clean-audit count
  - migration status

Daily audit CSVs are written to:
  output\christmas\live_audit\christmas_pdf_vs_live_YYYYMMDD.csv

The latest rolling CSV is:
  output\christmas\live_audit\christmas_pdf_vs_live_latest.csv

The comparison state used to detect day-to-day changes is:
  monitor_state\christmas_live_audit.json

Default confidence rules:
  3 consecutive clean/stable audits -> STABLE - BUILDING CONFIDENCE
  5 consecutive clean/stable audits -> READY TO REVIEW SWITCH

A clean audit means:
  - zero live image failures
  - zero PDF-vs-live price mismatches

These thresholds can be changed in daily_monitor_config.json under:
  christmas_audit

The original manual utility still works:
  run_christmas_live_audit.bat

No reprint is triggered merely because the PDF/live audit counts differ.
Reprints remain driven by genuine catalogue status changes such as SOLD OUT,
BACK IN STOCK, newly live items, or expiry/removal after the configured period.

