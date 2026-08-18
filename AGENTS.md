# AGENTS.md

## Purpose

This repository is an EzeGet consumer/presentation application for clearance and promotional catalogues. Agents working here must protect proven operational behaviour and avoid duplicating canonical supplier product/stock logic.

## Mandatory startup procedure

Before changing this repository:

1. Read this `AGENTS.md` in full.
2. Read `DEVELOPER_GUIDE.md` and the relevant sections of `OPERATIONS_GUIDE.md` when those files are present.
3. Check the current branch/PR and identify any in-progress work that overlaps the requested change.
4. Determine whether the requested behaviour belongs here or in a shared/canonical component before writing catalogue-specific code.
5. For VivaMK product/stock data, treat `stevegiergiel/VivaMk_Out_Of_Stock` as the canonical shared product/stock data layer unless the architecture contract is explicitly changed.

## Execution ownership: never monitor unassigned work

When a requested change requires implementation, assign/start the implementation work immediately before creating or relying on any progress monitor.

A monitor, scheduled check, reminder, issue, backlog entry, or readiness watcher is **not** an implementation agent and must never be represented as work being actively developed.

Before telling the user that work is underway, waiting for testing, or that they will be notified when it is ready, explicitly establish:

- who/what is implementing the change;
- the repository and branch/PR where the implementation will land;
- the minimum acceptance criteria for the milestone; and
- whether any monitor is merely watching that implementation.

If no implementation agent/process is actually available or assigned, say so immediately. Do not wait for the user to ask for a progress update before revealing that the task is unassigned.

If a task becomes blocked, abandoned, or loses its implementation owner, surface that promptly rather than continuing to report/watch it as though development is progressing.

### Handoff rule

For every implementation request use this sequence:

`REQUEST -> ASSIGN/START IMPLEMENTATION -> RECORD ACCEPTANCE CRITERIA -> IMPLEMENT -> TEST -> WATCH/NOTIFY IF USEFUL -> USER ACCEPTANCE -> MERGE`

Never use:

`REQUEST -> WATCH FOR COMPLETION`

unless an independently identified implementation process is already doing the work.

## Canonical VivaMK product/stock architecture

The intended data flow is:

`VivaMK site + VivaMK OOS spreadsheet -> canonical shared historical product database -> clearance booklet/iframe`

Do not create or maintain a competing implementation in this repository for generic VivaMK:

- stock detection/status semantics;
- product identity;
- normal/current price;
- canonical description;
- product URLs;
- image history;
- expected-back dates;
- product history.

Clearance-specific ownership includes sale membership, WAS/NOW prices, savings, booklet/iframe presentation, sale graphics, print layout, SOLD OUT display treatment, reprint alerts, and publishing.

Until the shared snapshot has passed live acceptance testing, proven clearance functionality may remain as a transitional fallback. Do not remove it prematurely and do not allow transitional evidence to redefine canonical status semantics.

## Stock safety rules

1. Missing from the shared snapshot does **not** mean SOLD OUT. Map missing/stale/contradictory evidence to `CHECK_REQUIRED` and, where appropriate, perform a supplemental exact-SKU sanity check.
2. Never convert a network failure, parser failure, missing image, blank page, suspiciously incomplete scrape, or failed refresh directly into `SOLD_OUT`.
3. Never overwrite known-good product data with blanks or weaker evidence.
4. Preserve prior descriptions, prices, URLs, images and statuses.
5. On catastrophically incomplete refreshes, retain last-known-good data and raise an alert.
6. Supplemental clearance checks may generate candidate discoveries for the canonical layer but must not silently create a competing local truth.
7. Once a SKU is credibly validated, failure of a later broad discovery crawl to rediscover it must not erase its known history.

## Definition of Done for a catalogue integration

A catalogue is not integrated merely because its booklet builds. Before calling a catalogue operationally complete, explicitly consider and test:

- source/config registration;
- booklet generation;
- iframe generation;
- inclusion in all-booklets/all-iframes runners where applicable;
- canonical/shared product-data lookup or approved transitional fallback;
- daily stock/SOLD OUT/status-change monitoring;
- persistent state/history behaviour;
- safe `CHECK_REQUIRED` handling;
- automatic regeneration after relevant changes;
- reprint alerts;
- Git/GitHub Pages publishing;
- live deployment verification;
- heartbeat reporting;
- unit/integration tests;
- documentation;
- rollback/recovery behaviour.

Anything intentionally deferred must be named as a follow-on patch/PR rather than silently omitted.

## Daily heartbeat contract

The daily heartbeat is an operational control, not merely an email saying a script ran. Changes affecting catalogues or stock/status behaviour must consider the complete chain:

`scheduled task -> refresh/check -> validate evidence -> compare previous state -> regenerate affected outputs -> publish -> verify deployment -> heartbeat -> local logs`

A received heartbeat must not be treated as proof that publishing/deployment succeeded. Report incomplete checks, failed refreshes, unpublished changes, or unverified deployments explicitly.

## Shared-component impact check

Before altering scraper/database/status logic, stop and check the canonical shared architecture contract. Shared changes belong on a separate branch/PR in the canonical repository and should be covered by unit/integration tests before consumer cutover.

Prefer one shared implementation over duplicated catalogue-specific implementations. If a change could affect more than one catalogue or consumer, assume it may belong in a common component until proven otherwise.

## Cutover safety

Do not switch clearance to a replacement shared snapshot path until:

- deterministic unit/integration tests are green;
- missing/failed evidence cannot produce false SOLD OUT states;
- shadow/live comparisons have been reviewed;
- last-known-good/rollback safeguards are demonstrated; and
- user acceptance has been obtained.
