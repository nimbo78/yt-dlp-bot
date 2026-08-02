# Roadmap

Planned work for this fork, with enough detail to start from. Items in
**Queued** are agreed and ordered; **Along the way** are small enough to attach
to whichever item is open; **Backlog** is specified but not scheduled.

Every claim about current behaviour below was checked against the code at the
time of writing, and the file references say where.

---

## Done

### Tests and CI

246 tests across the three packages, green, plus `.github/workflows/ci.yml`
running `ruff check` and `pytest` on push and pull request. Two deviations from
the plan below, both deliberate:

- **`bot/core/utils.py` is not covered.** Importing it pulls in Pyrogram and the
  whole config bootstrap for the sake of two small functions, which contradicts
  "pure functions, fast, no fakes". Testing it properly means first separating
  `split_telegram_message` and `can_remove_url_params` from `get_user_id`, which
  is a refactor rather than a test. Left for whenever that module is next
  touched.
- **Ruff needed settling before CI could be green.** Test code is held to
  different conventions than what it exercises, so `**/tests/**` carries
  per-file ignores in the root `pyproject.toml`, the README asset generator is
  excluded, and the ~30 findings in application code were fixed. A CI that is
  red on arrival teaches everyone to ignore it.

Two real bugs surfaced while writing the tests, both now fixed:

- `error_messages` did not recognise **"There's no video in this tweet"** — the
  apostrophe form, which is what X actually sends. The category existed and
  simply never fired.
- `ytdlp_logger.last_error()` raised `IndexError` on an empty message, *while
  already reporting a failed download*, replacing the real reason with a
  traceback about the reporting itself.

### Bearer token for the HTTP API

`API_TOKEN` in `envs/api.local.env`. Unset, the API accepts everything and the
port is published on `127.0.0.1` only, so an existing deployment keeps working
after the upgrade and nothing off the host can reach it; the service says so in
its log at startup. Set, every `/v1/…` route requires
`Authorization: Bearer <token>`, compared with `secrets.compare_digest`, and
Swagger UI grows an **Authorize** button.

`/status` stays open so health checks need no credential. `/docs` and
`/openapi.json` stay open too — they describe the API but expose no data, and
closing them would break the Authorize button. Both noted in the README.

15 tests drive the dependency through a one-route app rather than the real one,
which keeps Redis, RabbitMQ and the database out of a question that has nothing
to do with them.

### Free space check

`MIN_FREE_SPACE_MB` in `envs/worker.env`, default 512. Two checks: a floor
before anything starts, and a per-download one inside a yt-dlp progress hook,
which is where the size first becomes known without paying for an extra request.

The hook compares against `free + downloaded`, not `free` alone — the bytes
already written came out of the same space, and counting them twice would abort
a download that was going to fit.

Raising from the hook aborts the download, and because the worker runs yt-dlp
with `ignoreerrors` the message is collected by `YtdlpLogger` and travels the
existing failure path. So the refusal reaches the user through the same
classifier as everything else: a new `no_space` category, two keys across all 15
locales, plus a pattern for the kernel's own `no space left on device` for when
the disk fills anyway. Verified end to end against real yt-dlp, not only in unit
tests.

The plan said the size would come from `extract_info`; it does not. The worker
runs `extract_info(download=True)`, so metadata and file arrive together and by
then the space is already spent. A separate metadata call would have cost an
extra round trip, which on YouTube is exactly the request that draws the bot
check. The progress hook gets the same number for free.

### TTL for pending format choices

Entries carry a monotonic `added_at` and expire after 48 hours — monotonic on
purpose, so a clock correction cannot make one immortal or expire the lot.
Eviction happens on access **and** in an hourly `PendingCleanupTask`, because
eviction on access alone never reaches the entries nobody comes back to, which
are exactly the ones that accumulate.

Surviving a restart was explicitly out of scope and still is: the store lives in
the process, so `/restartbot` orphans every keyboard on screen and pressing one
answers "this request has expired", which is what happened. See the backlog.

### Quiet startup

One silent message to admins who kept `send_startup_message`, removed after
`telegram.startup_message_ttl` (default 3600, `0` keeps it). The greeting goes
out immediately and the version line is appended by editing it, so a slow
GitHub cannot cost you the "it came back" signal. No new locale keys: the two
halves are `start.startup` and `ytdlp.up_to_date` / `ytdlp.new_version`.

Silent by request — `disable_notification` on the send; editing never notifies
anyway. The recurring new-version notice is left alone: it asks for a rebuild.

Message ids live in Postgres, because nothing under `/app` survives the
container and `redeploy.sh` recreates it — which is the exact case the record
has to outlast. Persistence sits behind a small store interface rather than
inside the notice: importing `yt_shared.db.session` builds the engine at import
time and drags in asyncpg, which would have put a database driver on the path of
every bot unit test and in CI.

`send_startup_message` narrows to "an admin who has not opted out"; for
non-admins it is now inert, noted in `config-example.yml`.

This is the one place the suite uses fakes. The pure-functions boundary was
about not building machinery to reach trivial code; here the code deletes
messages in people's chats, and the orchestration is the behaviour.

---

## Queued

_Empty — everything agreed has shipped. The backlog below is specified but not
scheduled; pick from it whenever._

---

## Along the way

Small enough to attach to whichever item is open. Both of these went in with the
last of the queued work.

### ~~SoundCloud, and audio tags~~ — done

`--embed-metadata --embed-thumbnail` added to `AUDIO_YTDL_OPTS`. Artist, title
and cover reached the Telegram player as `send_audio` arguments already; now
they are inside the file too, so they survive being saved or forwarded
elsewhere.

Checked before shipping, because it was the risk: with `--write-thumbnail`
present yt-dlp constructs `EmbedThumbnailPP(already_have_thumbnail=True)`, so
the separate cover file the bot sends as a preview is kept rather than consumed.

This also revives `postprocess.metadata` and `postprocess.embed_thumbnail`,
which were mapped in the worker but never fired, leaving two dead keys in all 15
locales.

### ~~The false "up to date"~~ — done

The early `return` sat inside the inner `if`, so with a new version available
and `notify_users_on_new_version` off, control fell through and the bot reported
the version as current. Not covered by a test: reaching that method needs fakes
for the database, the GitHub client and the bot, which is the boundary the test
suite deliberately does not cross for a one-line control-flow fix.

---

## Backlog

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
