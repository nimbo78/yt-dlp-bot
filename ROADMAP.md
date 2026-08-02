# Roadmap

Planned work for this fork, with enough detail to start from. Items in
**Queued** are agreed and ordered; **Along the way** are small enough to attach
to whichever item is open; **Backlog** is specified but not scheduled.

Every claim about current behaviour below was checked against the code at the
time of writing, and the file references say where.

---

## Done

### Tests and CI

400 tests across the four packages, green, plus `.github/workflows/ci.yml`
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

The workflow later went red twice for reasons that had nothing to do with the
commits that triggered it, and both are now closed:

- **Pillow was missing from the install list.** The tests do not import it, but
  `yt_shared.schemas.media` does at module level, and `Chapter` lives there — so
  collecting `test_chapters.py` failed outright.
- **ruff was installed as `>=0.9`**, meaning whatever came out most recently.
  0.16 stabilised three preview rules and 185 findings appeared in an untouched
  tree. It is now pinned exactly; the library entries are still floors, because
  a new pytest does not invent new opinions and a new linter does. Moving the
  pin is a commit, with whatever the new release wants fixed in the same one —
  and rules that graduate into a release are listed in the root `pyproject.toml`
  with the reason they are not wanted here.

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

### `file_id` cache

The same link at the same media type and quality is answered from what Telegram
already holds. Nothing had ever read those ids back, so a repeat was a full
download for a byte-identical answer.

Matching needed three columns that did not exist: `task.download_media_type`,
`task.video_quality` and `file.file_type`. All nullable — rows written before
the migration cannot be given an answer, and guessing one would hand somebody
the wrong file. A partial hit is treated as a miss, so a request for audio *and*
video never comes back with only half.

Guarded in three places, because a wrong hit is the quiet kind of failure:

- skipped entirely when `save_to_storage` is on, since that setting exists to
  produce a file on disk and a cache hit produces none;
- a store that cannot be read is a miss, not a failed download;
- a refused id in the originating chat falls straight through to a real
  download, because nothing has reached the person who asked yet. A refusal in
  the forward group does not, since re-downloading would send them the file
  twice.

`/nocache <url>` forces a fresh download. The caption is built by a function
shared with the upload path, so a cached answer reads exactly like the first
one rather than subtly differently.

The lookup lives in the bot, not the worker: the worker would have to
reconstruct a `DownMedia` for files that are not on disk, and its validators
require paths that exist. The trade is that a cache hit records no task row, so
it does not appear in `/v1/tasks` — nothing was downloaded, but the history is
not complete either.

### Pending choices across restarts

The store moved out of the bot process, so `/restartbot` and `./redeploy.sh` no
longer orphan every keyboard on screen.

Postgres, not Redis. Redis is already running for the API and its TTL would have
come free, but the bot has no Redis client, and adding one relocks `app_bot` —
which breaks the image build until the lock is regenerated, and `uv` is not
available here to regenerate it. Postgres costs a migration and nothing else,
and `pgdata` is the volume that already survives `docker compose down`. Worth
noting that `yt_redis` has no volume at all, so it would not have survived one
either.

The user is stored by id and resolved from the configuration on read, so a
keyboard pressed after their settings changed uses the new ones — and one
pressed after they were removed from the configuration is simply gone.

`added_at` becomes a wall clock, where the in-memory version used a monotonic
reading: a monotonic value means nothing to the process that reads it back. The
trade is that a large clock correction can now age or rejuvenate an entry.

The expiry decision sits in `PendingDownloads` rather than in the store — the
first cut had the store compare against the cutoff, which put the only
interesting logic somewhere it could not be tested without a database.

This one took the whole stack down on first deploy, and the cause is worth
recording. `CustomBase` in `yt_shared/db/session.py` declares its primary key
as `id: uuid.UUID = sa.Column(...)` — a legacy annotation rather than
`Mapped[...]` — and SQLAlchemy 2.0.51 refuses to copy such an attribute into a
subclass, raising `MappedAnnotationError` at import time. All three services
import `yt_shared.models`, so all three crash-looped together.

Nobody had ever found out, because every model that shipped declares its own
`id` and so never inherits the annotated one. `PendingDownload` and
`StartupMessage` were the first that did not. Both now declare it, matching the
other five; the migrations already create the column, so nothing changed in the
database. `yt_shared/tests/test_models.py` reads the sources with `ast` and
holds the rule — importing the models to check it would build the engine and
put asyncpg on the path of a test that needs neither.

Two things made this reach production. The suite cannot import anything that
reaches `yt_shared.db.session`, so no test covered the models at all. And
`sqlalchemy>=2.0.37` floats: `yt_shared/uv.lock` pins 2.0.41, but the Dockerfiles
end with an unlocked `uv pip install -e ./yt_shared`, so the image resolved
2.0.51 — the same shape of surprise as the unpinned ruff above, on a day nothing
here changed. Fixing the base annotation properly, and deciding what to do about
the unlocked install, are both still open.

The migration behind it was wrong too, and for a plainer reason: it had never
been run. `c5f2a9d34e17` passed a `sa.Enum` to `op.create_table` for a type that
the same migration had just created, and `create_table` re-emits `CREATE TYPE`
from the table's before_create hook with `checkfirst` hard-coded to False — so
Postgres refused the duplicate and the whole chain rolled back. The type is now
declared `postgresql.ENUM(..., create_type=False)`. `add_column` fires no such
hook, which is why `b3d81f5c6e04` gets away with a plain `sa.Enum` and why
reading the two side by side suggests nothing is wrong.

Verified since against a real PostgreSQL 16 rather than by reasoning: the full
chain applies from an empty database to head, and downgrade-to-`50331b3c39bb`
and back up runs twice in a row. The second pass is the interesting one — the
downgrade deliberately leaves the shared enum behind, so it exercises the
"type already exists" path that failed in production. Standing up a throwaway
cluster costs about a minute and should be the rule for any future migration.

### A playlist link says it is one

`--no-playlist --playlist-items 1:1` means a link to a playlist, an album or a
channel produced exactly one file and said nothing about the rest — the worst
shape a wrong answer can take, because it looks like a success. Paste a
40-track album, get one track, and nothing on screen tells you which of the two
happened.

The format-selection message now carries a line saying so, for YouTube
playlists, channels and handles, SoundCloud sets, artist pages and tabs, Vimeo
albums, channels, showcases and groups, and Bandcamp albums and artist pages.

Detection is from the URL alone. Asking yt-dlp would be exact but costs a round
trip per pasted link before a format has even been chosen, and on YouTube that
is the request that draws the bot check.

`watch?v=…&list=…` is deliberately *not* flagged: that is what copying the
address bar during a playlist gives you, `--no-playlist` treats it as the one
video, and warning about it would put a notice on most YouTube links anyone
sends. The two mistakes do not cost the same — a missed collection leaves the
behaviour this fork has always had, a false positive nags on an everyday link —
so unrecognised hosts are answered "not a collection" and the tests are
exhaustive on the single-item side.

This is the honest minimum, not playlist support; see the backlog for the rest.

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

### RabbitMQ 3.12 is out of support

It says so itself on every boot: *"This release series has reached end of life
and is no longer supported."* Nothing is broken, and moving majors on a machine
this small is worth doing deliberately rather than as a side effect of some
other change.

### Pin what floats

Three separate failures in one day had the same cause: a dependency that was
free to move. `ruff>=0.9` reddened CI on a day nothing changed; `sqlalchemy>=2.0.37`
resolved to 2.0.51 and crash-looped all three services; `redis:alpine` moved to
Redis 8 and started loading four modules nobody uses. Each was fixed where it
bit. What is still open is the general case — chiefly the unlocked
`uv pip install -e ./yt_shared` at the end of every Dockerfile, which is why the
SQLAlchemy in the images is not the one `yt_shared/uv.lock` names. Regenerating
those locks needs `uv`, which is why it has not happened yet.

### JWT for the API

When there is more than one client with different rights. The bearer token
above covers the actual need for a self-hosted deployment.

### Playlists, actually downloading them

Saying so is done (above); doing it is not. The obstacle is not the yt-dlp
options, it is the pipeline: a task carries one `DownMedia`, the worker's
validators want paths that exist, and the bot renders progress for a single
file. Several items means several tasks, progress across them, a limit, and a
way to stop halfway — "download all 200" is not a feature on this hardware.

Worth doing only with a bound the user picks, something like "the first 10",
and worth pricing before starting: it touches the worker, the task model, the
upload path and the keyboard, which is more than any item shipped so far.

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
