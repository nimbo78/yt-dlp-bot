<p align="center">
  <img src="./assets/readme/hero.gif" width="100%"
       alt="yt-dlp-bot — a link is pasted in Telegram, format buttons appear, Video is chosen, the download reports its progress, processing takes over, and the finished file arrives in the same chat">
</p>

<p align="center">
  <b>Self-hosted Telegram bot for <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a>.</b>
  Runs on your own machine with Docker Compose. 🇺🇦
</p>

<p align="center">
  Version 1.7.2 · <a href="RELEASES.md">Release notes</a> ·
  Intended for videos under a Creative Commons licence
</p>

---

## Support the development

- [Buy me a coffee](https://www.buymeacoffee.com/terletsky)
- PayPal [![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donate_SM.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=MA6RKYAZH9DSA)
- Bitcoin `14kMRS8SvfD2ydMSMEyAmefHV3Yynf9kAd`

## What it does

Send a link to your bot. It asks what you want, downloads it, and sends the file
back — no browser, no desktop app, no files left on someone else's server.

- **Choose per download** — video, audio, or both; quality from 360p to 4K.
- **One status message** — a single message tracks the task from percentage and
  ETA through processing to upload, then makes way for the file itself.
- **Files that look right in Telegram** — source covers survive as thumbnails,
  and audio arrives tagged with its artist and track.
- **Chapters you can jump to** — when the source has them, the timestamps come
  along and Telegram seeks the file when you tap one.
- **The same link twice costs nothing** — Telegram already holds the file, so a
  repeat request is answered instantly instead of downloaded again.
- **Readable failures** — a suspended account, a private video or an expired
  cookie is explained in a sentence instead of a stack trace.
- **Speaks fifteen languages** — set one for everyone, or a different one per
  person.
- **Run it from the chat** — admins add users and change settings without
  touching the server.
- **Works headless too** — the same downloads can be triggered over HTTP.

## How it works

<p align="center">
  <img src="./assets/readme/architecture.svg" width="100%"
       alt="A link from the Telegram bot or the HTTP API is queued in RabbitMQ, downloaded by the worker with yt-dlp and FFmpeg, and the progress and result travel back through the same queue while PostgreSQL records every task">
</p>

Four services share one queue. The bot owns the conversation, the worker owns
the downloading, and neither blocks the other — so a three-hour video does not
stop the bot from answering.

## Quick start

**1. Get your Telegram credentials**

- Create a bot with [BotFather](https://t.me/BotFather) and copy its `token`.
- Get an `api_id` and `api_hash` from [my.telegram.org/apps](https://my.telegram.org/apps).
- Find [your Telegram user ID](https://stackoverflow.com/questions/32683992/find-out-my-own-user-id-for-sending-a-message-with-telegram-api).

**2. Write the config**

```bash
cp app_bot/config-example.yml app_bot/config.yml
```

Put the `token`, `api_id` and `api_hash` in place of the placeholders, then set
your own ID under `allowed_users` → `id`.

**3. Run it**

```bash
docker compose build base-image
docker compose up --build -d -t 0 && docker compose logs --tail 100 -f
```

The bot greets you with `✨ <YOUR_BOT_NAME> started, paste a video URL(s) to
start download`. Paste a link and it takes over from there.

Stop everything with `docker compose stop -t 0`.

**Rolling out changes later**

`redeploy.sh` rebuilds, restarts, and reclaims the disk space each rebuild
orphans — untagged images and excess build cache accumulate quietly until an
unrelated-looking service fails for want of space.

```bash
./redeploy.sh                 # rebuild and restart every application service
./redeploy.sh yt_bot          # only one service
./redeploy.sh --pull --base   # update the branch and rebuild the base image too
./redeploy.sh --clean-only    # just reclaim space
./redeploy.sh --help          # all options
```

## Telegram commands

Anyone allowed in the config can paste links. Admins get the rest:

| Command | What it does |
|---|---|
| `/adduser <telegram_id>` | Add a user with default settings |
| `/deleteuser <telegram_id>` | Remove a user — admins are protected |
| `/listusers` | Show everyone currently configured |
| `/config get <path>` | Read a value, e.g. `/config get telegram.max_upload_tasks` |
| `/config set <path> <value>` | Change a value, e.g. `/config set telegram.max_upload_tasks 5` |
| `/reloadconfig` | Re-read `config.yml` from disk |
| `/restartbot` | Restart the bot; Docker brings it back |

A format keyboard keeps working across a restart: the pending choice lives in
the database, not in the bot process, and expires after 48 hours.

Anyone allowed may also use `/nocache <url>` to download a link again, ignoring
the copy Telegram already holds.

Changes are written to `config.yml` and survive a restart.

## Configuration

**These are the files you edit. Nothing else.** Everything else in the
repository is a shipped default: edit one of those in place and every later
`git pull` stops with *"Your local changes would be overwritten by merge"*.
Every file in the left column is gitignored, so it survives each pull untouched.

| Edit | For | Shipped default it overrides |
|---|---|---|
| `app_bot/config.yml` | tokens, who may use the bot, per-user behaviour | `app_bot/config-example.yml` (copy it) |
| `envs/common.local.env` | settings shared by every service | `envs/common.env` |
| `envs/worker.local.env` | downloading, storage, thumbnails | `envs/worker.env` |
| `envs/api.local.env` | `API_TOKEN` for the HTTP API | `envs/api.env` |
| `envs/bot.local.env` | Telegram message limits | `envs/bot.env` |
| `docker-compose.override.yml` | volumes, memory limits, ports | `docker-compose.yml` |
| `app_worker/ytdl_opts/user.py` | raw yt-dlp options | `app_worker/ytdl_opts/default.py` (copy it) |

`./redeploy.sh` creates the `*.local.env` files empty if they are missing, so
they are there waiting the first time you look.

**How the env files layer.** Put your own values in a `*.local.env` next to the
shipped one; those are loaded last, so whatever you set there wins:

```sh
cat > envs/worker.local.env <<'EOF'
MAX_SIMULTANEOUS_DOWNLOADS=1
DOWNLOAD_RATE_LIMIT=2M
EOF
```

Only the keys you want to change need to be there — `common.local.env` reaches
every service, and `api`/`bot`/`worker.local.env` reach one each. See
[`envs/README.md`](envs/README.md), including how to move settings you have
already changed in place.

**Changing the Compose file.** Same rule as the env files: `docker-compose.yml`
is shipped as-is. Put machine-specific changes — where downloads land, how large
the staging area is, memory ceilings — in `docker-compose.override.yml`, which
Compose reads automatically and merges over it:

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

It is gitignored, and the example lists the changes people actually make.

**Where downloads are kept.** `STORAGE_PATH` in `envs/worker.env` is
`/filestorage` inside the container. Map it to a real directory for the
`yt_worker` service in your override file:

```yml
services:
  yt_worker:
    volumes:
      - "D:/Videos:/filestorage"
```

**Temporary space.** Downloads are staged in the `shared-tmpfs` volume, which is
**RAM-backed** and declared at 7 GB. Size it below the memory your host can
spare — see below if that is not much.

**Upload limits.** Telegram accepts 2 GB per file, or 4 GB with Premium. That
ceiling is `upload_video_max_file_size` in `config.yml`.

**Download speed.** Unlimited by default. `DOWNLOAD_RATE_LIMIT` in
`envs/worker.env` accepts a per-download rate such as `500K` or `4.2M`. It
applies to each download, so `2M` with `MAX_SIMULTANEOUS_DOWNLOADS=2` can still
use 4 MB/s in total.

**Parallel downloads.** `MAX_SIMULTANEOUS_DOWNLOADS` in `envs/worker.env`,
default 2. Raise it with the temporary space above in mind.

**Running out of room.** `MIN_FREE_SPACE_MB` in `envs/worker.env`, default 512,
is kept free in the staging area. A download is refused outright when less than
that is left, and again once yt-dlp reports a size that will not fit — a video
and its audio arrive as separate streams and are merged into a third, so about
three times the finished size has to be available. Either way the answer is a
readable "not enough disk space" rather than a half-merged file and a full disk.
`0` turns both checks off.

**Thumbnails.** `yt-dlp` keeps the source cover when it matches the video's
shape. Otherwise FFmpeg grabs a frame at `THUMBNAIL_FRAME_SECOND` seconds
(`envs/worker.env`), or at the midpoint for shorter videos.

**yt-dlp options.** Copy `app_worker/ytdl_opts/default.py` to `user.py` and edit
it; the worker prefers `user.py` when it is there and falls back to `default.py`
when it is not. `user.py` is gitignored, so it survives every pull. The
[full option list](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L180)
is upstream.

**Language.** Everything the bot says — buttons, progress, errors, admin
replies — is translated. `telegram.lang_code` in `config.yml` sets the language
for everyone; any user may choose their own:

```yml
telegram:
  lang_code: !!str "en"          # the default for everyone
  allowed_users:
    - id: 11111111111
      lang_code: !!str "uk"      # except this one
```

Available: `en` English, `be` Belarusian, `de` German, `el` Greek, `es` Spanish,
`fr` French, `he` Hebrew, `it` Italian, `kk` Kazakh, `lt` Lithuanian,
`lv` Latvian, `ru` Russian, `sr` Serbian (Cyrillic), `tt` Tatar,
`uk` Ukrainian. Anything else is rejected at startup with the list of valid values rather than
silently falling back. A translation missing a string falls back to English and
says so in the log.

Admins can switch the default without restarting:
`/config set telegram.lang_code uk`.

Translations live in `app_bot/bot/locales/<language>.json`. To add a language,
copy `en.json`, translate the values, and add its code to `LANGUAGES` in
`app_bot/bot/core/i18n.py`.

**Metadata language.** Separate from the above: this is the language the *video*
comes in, not the bot. YouTube serves titles, descriptions and chapters in
English by default, even for videos in another language, because that is what
the request asks for. Set `METADATA_LANGUAGE` in `envs/worker.env` to a tag such
as `ru` or `pt-BR` to prefer the translation the uploader provided. Where no
translation exists the original is returned unchanged. This applies to YouTube;
other sites decide for themselves.

**Logging.** `LOG_LEVEL` in `envs/common.env`.

**Repeat downloads.** When the same link is asked for at the same media type
and quality, the file Telegram is already storing is sent back instead of being
downloaded again — no traffic, no CPU, no disk, no wait. The status message says
so before the file arrives, and nothing is left in the chat to say it afterwards.

The cache is only ever an optimisation: if Telegram no longer accepts the stored
id, the download proceeds as normal. It is skipped for a user with
`save_to_storage` on, since the point of that setting is a file on disk and a
cache hit produces none. `/nocache <url>` forces a fresh download when a stored
copy is stale.

**A quiet start.** When the bot comes up it posts one message — a greeting, with
the yt-dlp version appended to it once that check finishes — to admins who kept
`send_startup_message`, without a notification sound, and removes it again after
`telegram.startup_message_ttl` seconds (default 3600, `0` keeps it). The ids are
recorded so that a restart within that window clears the previous one rather
than orphaning it.

The recurring "a new yt-dlp version is out" notice is not removed: it asks you
to rebuild the worker, and a call to action that evaporates overnight is worse
than none.

**Tidying the chat.** `telegram.delete_source_message` removes the message a
link arrived in once the file has been delivered — the caption on the file
already carries the link. It applies to everyone, and any user can override it:

```yml
telegram:
  delete_source_message: !!bool True   # the default for everyone
  allowed_users:
    - id: 11111111111
      delete_source_message: !!bool False   # except this one
```

Off unless you turn it on. It only runs after a successful upload, so a failure
never costs you the link you need to retry with, and it needs the bot to be an
administrator in group chats. Telegram refuses to delete anything older than 48
hours; a refusal is logged and otherwise ignored.

Admins can flip it without restarting: `/config set telegram.delete_source_message true`.

### Running with limited resources

On a small VPS the default staging area is the thing most likely to hurt you.
`shared-tmpfs` is RAM, so a download larger than your free memory does not fail
politely — it fills RAM, spills into swap, and the whole host stops responding
while the kernel thrashes. The bot, the API and SSH all go down with it, and
nothing in the application layer can prevent that.

Two changes make a small machine safe.

**Stage downloads on disk instead of in RAM.** Mount a host directory over the
staging path in both services that use it. The bind replaces the `shared-tmpfs`
volume by mount target, so that volume is simply left unused — nothing to remove
and nothing to recreate. In `docker-compose.override.yml`:

```yml
services:
  yt_bot:
    volumes:
      - "/var/lib/yt-dlp-bot/staging:/tmp/download_tmpfs"
  yt_worker:
    volumes:
      - "/var/lib/yt-dlp-bot/staging:/tmp/download_tmpfs"
```

Create the directory first; Docker would otherwise create it as root. Downloads
are then bounded by free disk rather than free memory, and a file too large
simply fails with "no space left on device".

To keep it in RAM but make it smaller, override the size instead. That does not
resize an existing volume — Docker only creates one that does not exist yet — so
remove it once, and that one only, because `pgdata` holds the task history:

```yml
volumes:
  shared-tmpfs:
    driver_opts:
      o: "size=2048m,uid=1000"
```

```bash
docker compose down
docker volume rm "${COMPOSE_PROJECT_NAME:-yt}_shared-tmpfs"
docker compose up -d
```

**Give each service a memory ceiling** so a runaway container is killed instead
of the host. This one goes in `docker-compose.override.yml`:

```yml
services:
  yt_worker:
    mem_limit: 512m
    memswap_limit: 512m   # equal to mem_limit forbids swap for this container
```

This is enforced by the kernel, which is the point: a monitoring script cannot
help once the machine is thrashing, because it will not be scheduled or able to
allocate. A cgroup limit acts immediately and cannot be starved. Combined with
the `restart: unless-stopped` the services already carry, the worst case becomes
one failed download and an automatic restart rather than a machine you have to
power-cycle.

Also lower `MAX_SIMULTANEOUS_DOWNLOADS`, and consider `DOWNLOAD_RATE_LIMIT` if
the bot shares its connection with anything you care about — both in
`envs/worker.local.env`.

**Watch `API_WORKERS`.** Each uvicorn worker is a separate process holding a
full copy of the application, so the shipped default of 1 is deliberate: the API
hands a request to the queue and nothing else, and raising it multiplies
resident memory for no throughput anyone here needs. A container that exits with
**137** was killed by the kernel, not by the application, and on a small host
this is the usual reason.

**The supporting services are trimmed for this too**, and both are worth knowing
about before you change them:

- **Redis** is pinned to `redis:7-alpine`. The floating `redis:alpine` tag moved
  to Redis 8, which bundles RedisBloom, RediSearch, RedisTimeSeries and ReJSON
  into the base image and loads all four at startup. Redis is used here in one
  place only — the `fastapi-cache` backend in `app_api/api/app.py` — which needs
  none of them. It also runs with `--maxmemory 64mb --maxmemory-policy
  allkeys-lru`: there is no volume behind it, so nothing there is worth keeping
  and the only real risk was unbounded growth.
- **RabbitMQ** loads only the management plugin, via `rabbitmq/enabled_plugins`.
  The `-management` image also enables `rabbitmq_prometheus`, and nothing in
  this stack scrapes it. The UI on 15672 is unaffected.

RabbitMQ's **memory high watermark** is set to 192 MiB in `rabbitmq/memory.conf`,
down from the default 40% of host RAM. This is the point at which the broker
blocks publishers to stop growing — not a limit on what it uses — so it protects
the host under load rather than freeing anything at rest. The figure comes from
a measurement: 70 MiB idle with three queues, and messages here are small JSON
payloads. Below what the broker actually needs, the bot would hang trying to
queue a download, so take your own reading before lowering it further:

```bash
docker stats --no-stream yt_rabbitmq
```

On a larger host, raise it or use `vm_memory_high_watermark.relative = 0.4`
instead. Whatever is in effect is announced on every boot — `Memory high
watermark set to ...` in the RabbitMQ log.

## Cookies

Some sites only serve content to an authenticated session. Export your cookies
in **Netscape format** into `app_worker/cookies/`. Two filenames are recognised:

| File | In git? | Priority | Use it for |
|---|---|---|---|
| `_cookies.txt` | ❌ ignored via `**/_cookies.txt` | **highest** | ✅ your real cookies |
| `cookies.txt` | ✅ committed placeholder | fallback | leave it empty |

**Put real cookies only in `_cookies.txt`.** Cookie files hold live session
tokens. `cookies.txt` is tracked by git, so anything written there appears in
`git status` and can be published by accident. The underscore-prefixed name
exists to prevent exactly that. Keep the empty `cookies.txt` in place — it is
the placeholder the fallback expects.

Cookies are copied into the worker image at build time, so updating them needs a
rebuild:

```bash
cp /path/to/exported.txt app_worker/cookies/_cookies.txt

git status --short app_worker/cookies/    # must print nothing

./redeploy.sh yt_worker
```

**YouTube is handled the other way round.** There, an authenticated session
coming from a server address draws the bot check far more readily than no
session at all, so downloads start anonymously and the cookie file is only
brought in if the site actually asks for one — for an age-restricted, private
or members-only video. Every other host still sends cookies first and falls
back to anonymous if the session is rejected. Either way the worker makes at
most one extra attempt and says so in the status message.

Cookies exported from a browser you stay signed into are rotated away within
hours. Export from a private window and close it *without* logging out.

## HTTP API

Runs on port `1984`, published on `127.0.0.1` only. Interactive docs at
`http://127.0.0.1:1984/docs`.

**Set a token before exposing it.** The API queues downloads into the chats the
bot is configured for, so reaching it is enough to make the bot send files to
them. Two things keep that shut, and either one alone is sufficient:

```sh
echo 'API_TOKEN=put-a-long-random-value-here' >> envs/api.local.env
```

With `API_TOKEN` set, every `/v1/…` route requires a header, and Swagger UI
grows an **Authorize** button:

```bash
curl -H "Authorization: Bearer $API_TOKEN" http://127.0.0.1:1984/v1/tasks/stats
```

With it unset the API accepts everything, which is safe only because the port
is bound to the host — the service says as much in its log at startup. To reach
it from elsewhere, set the token *and* republish the port in
`docker-compose.override.yml`.

`/status` stays open either way, so health checks and uptime monitors need no
credential. `/docs` and `/openapi.json` also stay open: they describe the API
but expose no data, and locking them would break the Authorize button.

| Endpoint | Method | Description |
|---|---|---|
| `/status` | `GET` | Health check, normally `{"status": "OK"}` |
| `/v1/yt-dlp` | `GET` | Installed and latest `yt-dlp` version |
| `/v1/tasks` | `POST` | Queue a download from `{"url": "<URL>"}` |
| `/v1/tasks/?include_meta=False&status=DONE` | `GET` | List tasks, filtered by `PENDING`, `PROCESSING`, `FAILED` or `DONE` |
| `/v1/tasks/<id>?include_meta=True` | `GET` | One task by ID |
| `/v1/tasks/latest?include_meta=True` | `GET` | The most recent task |
| `/v1/tasks/<id>` | `DELETE` | Delete a task |
| `/v1/tasks/stats` | `GET` | Overall counts |

Queueing a download:

```json
{
    "url": "https://www.youtube.com/watch?v=PavYAOpVpJI",
    "download_media_type": "AUDIO_VIDEO",
    "video_quality": "1080P",
    "save_to_storage": false,
    "custom_filename": "cool.mp4",
    "automatic_extension": false
}
```

`video_quality` accepts `BEST` (default), `4K`, `1440P`, `1080P`, `720P`, `480P`
and `360P`. The response carries the task `id` to poll:

```json
{
    "id": "5ac05808-b29c-40d6-b250-07e3e769d8a6",
    "url": "https://www.youtube.com/watch?v=PavYAOpVpJI",
    "source": "API",
    "added_at": "2022-02-14T00:35:25.419962+00:00"
}
```

RabbitMQ and PostgreSQL credentials default to the values in `envs/common.env`;
change them in `envs/common.local.env`. The API port is in `docker-compose.yml`.
