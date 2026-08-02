# Roadmap

Planned work for this fork, with enough detail to start from. Items in
**Queued** are agreed and ordered; **Along the way** are small enough to attach
to whichever item is open; **Backlog** is specified but not scheduled.

Every claim about current behaviour below was checked against the code at the
time of writing, and the file references say where.

---

## Queued

### 1. Tests and CI

**Why now.** There are no tests and no CI in the repository. Meanwhile the last
few rounds of work added a layer of logic that is easy to break silently and
tedious to check by hand — most of all the ordered regex table in
`app_bot/bot/core/error_messages.py`, where correctness depends on the order of
the tuple, not just its contents. Locale key and placeholder parity has been
verified with throwaway scripts so far; that belongs in a test.

**Layout.** Per package — `app_bot/tests/`, `app_worker/tests/`,
`yt_shared/tests/`. Imports in this project are rooted at the package directory
(`from bot.core...`) and `yt_shared` is installed editable, so per-package tests
need no path juggling. A single root `tests/` would.

**Tooling.** `pytest` as a dev dependency of each package. No `pytest-asyncio`
in this round — nothing asynchronous is in scope.

**Covered.** Pure functions only:

| Module | Cases |
| --- | --- |
| `error_messages` | every one of the 19 categories against real yt-dlp strings; **ordering** specifically: DRM before everything, `private` before the broad `sign in`, the typographic apostrophe in `you're not a bot` |
| `i18n` | key and placeholder parity across all 15 locales; English fallback; `has_message` for keys arriving from the worker |
| `chapters` | `format_timestamp` past an hour; `group_into_messages` splitting only between lines, never mid-chapter |
| `progress` | every stage; missing optional fields; an unknown `detail_key` |
| `config_manager` | `_resolve_declared_type` through nested paths and `Optional`; `_convert_value` for bool, int, str |
| `utils` | `split_telegram_message`, `can_remove_url_params` |

**Not covered, deliberately.** Pyrogram handlers, RabbitMQ, the database.
Reaching them needs fakes, and that is the boundary this round does not cross —
which is also why no mocks are needed anywhere above: everything listed is a
pure function.

**CI.** `.github/workflows/ci.yml` running `ruff check` and `pytest` on push and
pull request, Python 3.12, no Docker and no network.

**Done when** the suite passes locally and in Actions, and a deliberate
reordering of two `_PATTERNS` entries makes it fail.

---

### 2. Bearer token for the HTTP API

**Why now.** `docker-compose.yml` publishes `1984:8000` on every interface and
the API has no authentication at all — the README says so outright. Anyone who
reaches the port can queue downloads into the configured chats. This is a hole,
not a feature, and it is small.

**Behaviour.**

- `API_TOKEN` read from `envs/api.local.env`.
- Token empty: the service still starts, and the published port becomes
  `127.0.0.1:1984:8000` so only the host can reach it.
- Token set: a FastAPI dependency requires `Authorization: Bearer <token>`,
  compared with `secrets.compare_digest`. Exposing the port beyond localhost is
  then the operator's choice, made in `docker-compose.override.yml`.
- `/status` stays open so health checks keep working. Everything else is closed.

**Also.** Rewrite the README's HTTP API section, which currently advertises the
absence of authentication as a fact of life.

**Done when** an unauthenticated request to `/v1/tasks` returns 401, an
authenticated one succeeds, and a default `docker compose up` leaves nothing
listening beyond the host.

---

### 3. Free space check before downloading

**Why now.** The disk has filled twice. Today that is discovered when FFmpeg is
already halfway through merging, which wastes the download and leaves debris.

**Two stages, because one is not enough.**

1. **Floor**, before anything starts: `shutil.disk_usage()` on
   `TMP_DOWNLOAD_ROOT_PATH` against `MIN_FREE_SPACE_MB` from `envs/worker.env`.
   Cheap, and catches "the disk is already full".
2. **Per item**, after `extract_info`, where `filesize_approx` is already
   available: roughly `3 × size` is needed — video, audio, and the merged
   result — plus the floor. Catches "this particular video will not fit".

**Refusal** goes through the machinery that already exists: a new `no_space`
category in `FriendlyError`, with its emoji, title and explanation. This is the
real cost of the item: **two new keys × 15 locales**.

Add a pattern for `no space left on device` as well, so a failure that happens
anyway — because the estimate was wrong or something else ate the disk
meanwhile — is explained by the same category instead of a raw dump.

**Done when** a download is refused with a readable message on a deliberately
filled staging directory, and nothing is left behind.

---

### 4. TTL for pending format choices

**Why now.** `PendingDownloadsStore` is a plain `ClassVar` dict
(`app_bot/bot/core/pending_downloads.py`) with no eviction. Every link that was
pasted and never answered stays in it for the life of the process. On a bot that
runs for months that is a slow leak.

**Behaviour.** Each `PendingDownload` carries a timestamp; entries older than
the TTL are dropped. **48 hours** — a keyboard nobody touched in two days will
not be touched. Sweeping is lazy on access **plus** a periodic task, because
lazy alone never reaches a key nobody returns to. The existing `DbCleanupTask`
is the pattern to copy.

**Explicitly not in scope.** This does not make pending choices survive a
restart. `/restartbot` will still orphan every keyboard on screen, because the
dict lives in the process. That is a separate decision — see the backlog.

**Done when** an entry disappears after the TTL, the periodic sweep is observed
in the log, and the store does not grow across a long idle period.

---

## Along the way

Small enough to attach to whichever item is open.

### SoundCloud, and audio tags generally

SoundCloud downloads work today, and the Telegram player shows artist and title
correctly — but only because `app_bot/bot/core/tasks/upload.py` passes them to
`send_audio` as `performer` and `title`. **The MP3 itself carries no tags.**
`AUDIO_YTDL_OPTS` in `app_worker/ytdl_opts/default.py` has neither
`--embed-metadata` nor `--embed-thumbnail`, so saving the file elsewhere loses
the artist, the title and the cover.

A side effect: `_STEP_KEYS` in `app_worker/worker/core/progress.py` maps the
`FFmpegMetadata` and `EmbedThumbnail` post-processors, but neither ever runs,
which makes `postprocess.metadata` and `postprocess.embed_thumbnail` dead keys
in all 15 locales.

Two flags fix the file, the dead keys, and the missing covers at once.

### The false "up to date"

`app_bot/bot/core/tasks/ytdlp.py:64-74` — the early `return` sits inside the
inner `if`, so when a new version exists **and** `notify_users_on_new_version`
is false, control falls through and the bot reports the version as up to date.
It is not. Only reachable with notifications disabled, which is why it has gone
unnoticed.

---

## Backlog

### Quiet startup — specified, ready to pick up

**Today.** Two messages on every restart. `_notify_outdated` goes to admins
only, which is right; the greeting and `_notify_up_to_date` go to everyone with
`send_startup_message: true` — including people who cannot act on a yt-dlp
version at all. Restarts are frequent here, so the chat accumulates them.

**Target.** One message, to admins, that removes itself.

- **Recipients:** admins ∩ `send_startup_message`. The flag survives as an
  opt-out for an admin who does not want the notice; non-admins never receive
  one. Its meaning narrows — worth a note in `config-example.yml`.
- **One message, built in two steps.** The greeting is sent immediately; when
  the version check finishes, that same message is **edited** to append the
  version line. Waiting for the check instead would mean no greeting at all
  whenever GitHub is slow or down.
- **No new locale keys.** The two halves are the existing `start.startup` and
  `ytdlp.up_to_date` / `ytdlp.new_version`, joined with a newline.
- **TTL:** `telegram.startup_message_ttl` in `config.yml`, default `3600`, `0`
  keeps the message. Changeable live through `/config set`.
- **The periodic "new version" notice is not deleted.** It asks the reader to
  rebuild the worker; a call to action that evaporates overnight is worse than
  no notice. Only startup noise is ephemeral.

**The one awkward part is bookkeeping.** The timer lives in the process, so a
restart inside the TTL window orphans the message forever — and startup messages
appear precisely at restarts. So the sent message ids are recorded, and the next
startup deletes the previous batch before sending a new one: the timer handles
the normal case, the startup sweep handles the crash case.

Storage: **PostgreSQL**, which the bot already talks to and which already has
Alembic, so no new dependency and a trivial migration. Redis is the alternative
— it is already running for the API and gives TTL for free — at the cost of a
dependency the bot does not currently have.

Telegram refuses to delete anything older than **48 hours**; when the bot has
been down longer, log it and move on, as already done for source-message
deletion.

Fold in the two `ytdlp.py` fixes above while in that file.

### `file_id` cache — the largest single win

`cache_id`, `cache_unique_id`, the model and `save_file_cache()` all exist and
are written on every upload. **Nothing ever reads them**, so the same URL sent
twice downloads from scratch.

- `file_id` survives deletion of the message that carried it, which matters here
  because the status message and often the source message are deleted.
- It is bound to the bot token; changing the token invalidates the cache.
- It is not guaranteed permanent, so the design must be: try to send by
  `file_id`, catch the failure, fall back to a normal download. The cache is an
  optimisation, never a source of truth.
- Key: URL + media type + quality. URL normalisation is the sharp edge —
  `youtu.be/X`, `watch?v=X` and `?si=…` are one video and three keys.
  `REMOVE_QUERY_PARAMS_HOSTS` covers part of it. A canonical extractor id would
  be better but costs a network round trip, which on YouTube is the expensive
  part.
- Tell the user it was a cache hit, but leave no trace: a line in the status
  message, which is deleted on success anyway, plus a toast on the button. Never
  in the file caption — that is permanent. Provide a way to bypass, either a
  "download again" button or `/nocache <url>`.

Worth doing after the tests exist: a wrong cache hit is a quiet, embarrassing
failure, and that is exactly the kind a test suite makes safe to work on.

### JWT for the API

When there is more than one client with different rights. The bearer token
above covers the actual need for a self-hosted deployment.

### Playlists

`--no-playlist --playlist-items 1:1` in `app_worker/ytdl_opts/default.py` means
a playlist link silently yields only the first video, with no warning. The
minimum honest step is to detect a playlist and say so. Full support needs a
choice or a filter — "download all 200" is not a feature on this hardware — plus
progress across several tasks, limits and cancellation.

### Pending choices across restarts

The other half of item 4. Needs a store that outlives the process; Redis is
already running for the API.

---

## Constraints worth keeping in mind

- **Any new user-facing string costs 15 translations.** It is worth asking
  whether an existing key can be reused before adding one — the quiet-startup
  item avoids new keys entirely by composing two that already exist.
- **Telegram will not delete a message older than 48 hours.** Anything built on
  deletion needs a path for when that fails.
- **The host is small** — under 1 GB of RAM, staging on disk, memory ceilings in
  `docker-compose.override.yml`. Features that assume spare capacity do not fit.
- **This is a fork that still merges from upstream.** Shipped files stay as
  shipped; local settings live in `envs/*.local.env`,
  `docker-compose.override.yml` and `app_worker/ytdl_opts/user.py`.
