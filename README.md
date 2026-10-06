# Clarence

A multipurpose Discord bot: a Rythm-style music player, full moderation suite with AutoMod and logging,
flight tracking, Texas Hold'em, trivia, translation and a pile of fun commands.

Every command is a **slash command**. Type `/` in Discord to browse them, or run `/help`.
Right-click a user or message → **Apps** for quick actions (User Info, Warn, Mod History, Translate to English, Ratio).

## Warning
`constants/words.txt` is a list of ~1000 swear words (used by the optional built-in AutoMod word filter).
If you're sensitive to that, don't open it.

---

## Setup

### 1. Environment variables

Put these in `keys.env` for local runs, or in the Railway service's **Variables** tab.

| Variable | Required | What it's for |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token |
| `DEV_GUILD_ID` | recommended | Your private server's ID. Owner-only commands (`/dashboard`, `/reload`, `/sync`, `/shutdown`…) are registered **only** here so nobody else sees them. If unset, owner commands are disabled. |
| `DATA_DIR` | recommended | Where all persistent data is stored. Set to your Railway volume's mount path (e.g. `/data`). Defaults to `storage/`. |
| `LAVALINK_URI` | for music | Lavalink server URL, e.g. `http://lavalink.railway.internal:2333`. Default `http://localhost:2333`. |
| `LAVALINK_PASSWORD` | for music | Must match the Lavalink server's password. Default `youshallnotpass`. |
| `AERODATABOX_KEY` | for flight schedules | Free RapidAPI key for [AeroDataBox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox) (Basic plan). Powers `/flight status`, `/flight route`, `/flight departures`, `/flight arrivals`. Everything else in aviation works without it. |
| `TENORKEY` | optional | Google Tenor v2 API key for `/gif` |
| `ai` | optional | DeepAI key for `/ai` |

### 2. Invite link
The bot needs the `applications.commands` scope for slash commands:
`https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot%20applications.commands`

In the Developer Portal, enable the **Server Members** and **Message Content** privileged intents (Presence isn't needed).

### 3. Run locally
```bash
docker compose up --build      # starts Lavalink + the bot (reads keys.env)
```
or without Docker:
```bash
pip install -r requirements.txt
docker compose up lavalink     # music needs a Lavalink server (Java 17+ also works: see lavalink/)
python main.py
```

Slash commands sync automatically on startup, but only when they've changed, because Discord rate-limits syncing.
Use `/sync` in your dev server to force it.

---

## Deploying on Railway

Clarence runs as **two services** in one Railway project.

**1. Bot service** (repo root)
- Builds from the root `Dockerfile`.
- Attach a **Volume** mounted at `/data` and set `DATA_DIR=/data`. Everything persistent lives there:
  mod cases, warnings, notes, server config, AutoMod settings, poker balances, trivia stats, music volume, and the cached airport database.
- If you have data from the old setup in `storage/*.json`, copy those files into the volume once.

**2. Lavalink service** (music)
- New service from the same repo with **Root Directory** = `lavalink`. It builds `lavalink/Dockerfile`.
- Variables: `LAVALINK_SERVER_PASSWORD=<something secret>`, `SERVER_ADDRESS=::` (for Railway private networking).
- On the bot service set `LAVALINK_URI=http://<lavalink-service-name>.railway.internal:2333` and `LAVALINK_PASSWORD` to the same secret.
- Turn on **Settings → Serverless (App Sleeping)**. The bot only connects to Lavalink when someone uses a
  music command and disconnects after 3 idle minutes (`LAVALINK_IDLE_SECONDS` on the bot service), so Lavalink
  sleeps and costs almost nothing while nobody's listening. The first `/play` after it sleeps takes ~15–40s to wake it.
- It runs in ~350–450 MB RAM (256 MB Java heap, set in `lavalink/Dockerfile`).

### Keeping the bill down
- Leave **App Sleeping off on the bot service**: it holds a permanent Discord connection, so it would never sleep anyway.
- Don't add replicas, and set no more than ~0.5 vCPU / 512 MB as the per-service limit so a runaway can't run up costs.
- The bot doesn't request the presences intent (it's the noisiest Discord event and was the bot's biggest RAM/CPU cost),
  so you can turn **Presence Intent** off in the Developer Portal.

### About YouTube
No cookies, OAuth or YouTube accounts are used. Lavalink's [youtube-source](https://github.com/lavalink-devs/youtube-source)
plugin plays YouTube anonymously. YouTube sometimes blocks datacenter IPs like Railway's ("confirm you're not a bot").
When a track fails that way, the bot automatically retries the same song from **SoundCloud**.

**Spotify links** (optional): create a free app at the [Spotify developer dashboard](https://developer.spotify.com/dashboard)
(this is an API app, not a login) and set `SPOTIFY_ENABLED=true`, `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` on the **Lavalink** service.
Spotify tracks are matched and played from YouTube Music or SoundCloud. Apple Music links work without any setup.

---

## Commands

### 🎵 Music
| Command | |
|---|---|
| `/play <song or URL>` | Search (with autocomplete) or paste a YouTube / SoundCloud / Spotify / Apple Music link or playlist |
| `/playnext <song>` | Put a song at the front of the queue |
| `/playskip <song>` | Skip the current song and play this one now |
| `/queue` | Paginated queue with total length |
| `/nowplaying` | Current song, progress bar, and ⏯️ ⏭️ ⏹️ 🔁 🔀 buttons (also posted automatically when each song starts) |
| `/skip`, `/skipto <n>`, `/pause`, `/resume`, `/stop`, `/replay` | Playback control |
| `/seek <1:30>`, `/volume <0-150>` | Position and volume (volume is remembered per server) |
| `/loop off\|track\|queue`, `/shuffle`, `/autoplay` | Queue modes. Autoplay keeps playing similar songs when the queue runs out |
| `/remove <n>`, `/move <from> <to>`, `/clearqueue` | Edit the queue |
| `/filter` | Bass boost, nightcore, vaporwave, 8D, karaoke, soft |
| `/join`, `/leave` | The bot also leaves after 5 min idle or 2 min alone |
| `/lyrics [song]` | Lyrics for the current song or any search ([LRCLIB](https://lrclib.net), no key needed) |

### 🛡️ Moderation
Commands are hidden from members who lack the matching permission. Every action is recorded as a numbered **case**.

| Command | |
|---|---|
| `/ban <user> [reason] [duration] [delete_messages]` | Permanent or temporary ban. Works on users not in the server. Tempbans lift automatically |
| `/unban <user>` | Autocompletes from the ban list |
| `/softban`, `/kick`, `/timeout <duration>`, `/untimeout` | |
| `/warn <member> <reason>` | Warns and DMs the member. May trigger escalation (below) |
| `/warnings list\|remove\|clear` | View or pardon warnings |
| `/case view\|reason\|history` | Look up a case, edit its reason, or see a user's full history |
| `/note add\|list\|remove` | Private moderator notes on a user |
| `/purge <amount> [user] [contains] [bots] [attachments] [links]` | Filtered bulk delete (pinned messages are kept) |
| `/lock`, `/unlock`, `/slowmode` | Channel controls |
| `/lockdown start\|end` | Lock every text channel, then restore exactly what was there before |
| `/nick`, `/role add\|remove\|info\|list` | Member and role tools (respects role hierarchy) |
| `/vc move\|moveall\|disconnect\|mute\|deafen` | Voice moderation |
| `/serverinfo`, `/banlist` | |

### ⚙️ Server config & logging (`/config`, needs Manage Server)
| Command | |
|---|---|
| `/config logging enable` | Creates a private **🔒 Clarence Logs** category with `#mod-log` (mod actions, AutoMod hits) and `#server-log` (edits, deletes, joins/leaves, role/nickname/timeout changes, voice, channel and role changes). Only roles with moderator permissions can see it |
| `/config logging addrole\|disable\|channels` | Give another role access, turn logging off (optionally deleting the channels), or use existing channels instead |
| `/config escalation set\|remove\|list` | Automatic punishments at N active warnings, e.g. 3 → 1h timeout, 5 → kick, 7 → ban |
| `/config welcome`, `/config goodbye` | Join/leave messages. Placeholders: `{user}` `{name}` `{server}` `{count}` |
| `/config autorole add\|remove` | Roles given on join (separately for humans and bots) |
| `/config view` | Show everything |

### 🤖 AutoMod (`/automod`, needs Manage Server)
**Off by default in every server.** Each server turns it on with `/automod toggle enabled:True`.
The first time it's enabled, the spam, mention and invite filters are switched on.

- Filters: **spam** (N messages in N seconds), **mentions** (mass pings), **invites** (discord.gg links),
  **links** (all links except allowed domains), **words** (custom list + optional built-in list, catches leetspeak), **caps**
- `/automod action`: delete only, delete + warn (counts toward escalation), or delete + timeout
- `/automod exempt role|channel`. Members with Manage Messages are always exempt
- `/automod status` shows the full configuration

### ✈️ Aviation
| Command | |
|---|---|
| `/flight track <UA1 \| UAL1 \| N12004 \| a05627>` | Live position, altitude, speed, route, distance and ETA to destination, aircraft type and photo, links to live map, FlightAware and FR24 |
| `/flight aircraft <registration or hex>` | Aircraft details, owner, photo, and whether it's flying now |
| `/flight nearby <airport> [radius]` | Everything in the air around an airport right now |
| `/flight status <number> [date]` | Scheduled, estimated and actual times, terminal, gate, baggage belt, delays *(AeroDataBox)* |
| `/flight route <origin> <destination> [date]` | Direct flights between two airports *(AeroDataBox)* |
| `/flight departures\|arrivals <airport> [hours]` | Airport departure/arrival board *(AeroDataBox)* |
| `/airport info <airport>` | Codes, location, elevation, current weather, live traffic count, map links |
| `/airport weather <airport>` | Decoded METAR plus raw TAF |

Airports autocomplete by IATA, ICAO, name or city. Data sources: [adsb.lol](https://adsb.lol), [adsbdb](https://www.adsbdb.com),
[OurAirports](https://ourairports.com), [aviationweather.gov](https://aviationweather.gov) and [AeroDataBox](https://aerodatabox.com).

### 🎰 Poker (`/poker`)
Full Texas Hold'em with everyone who joins:
- `/poker start [blinds]` opens a table in the channel. Players press **Join**, then the host presses **Start** (2–9 players).
- Correct button and blind rotation (including heads-up), minimum-raise rules, all-ins and **side pots**, split pots.
- Act with buttons (Fold / Check / Call / Raise / All-in). **🃏 My cards** shows your hole cards and current hand privately.
- People can join or leave between hands. The game continues until one player has all the chips or `/poker end`.
- Chips persist per server: `/poker balance`, `/poker leaderboard`, `/poker refill` (500 chips once a day when you're low), `/poker give` (admins).
- Missing your turn twice in a row removes you from the table.

### 🎮 Games & fun
`/trivia play|stats|leaderboard`, `/fizzbuzz` (buttons), `/count`, `/fiftytwo`, `/8ball`, `/dice`, `/coinflip`,
`/emojify`, `/nft`, `/paradigm`, `/shutup`, `/bored`, `/facepalm`, `/joke`, `/insult`, `/compliment`, `/pickup`,
`/xkcd`, `/animal`, `/gif`, `/wikipedia`, `/ascii`, `/bug`, `/hello`

### 🧮 Utility
`/translate` (or react to any message with a country flag 🇫🇷), `/detect`, `/languages`, `/latex`, `/bits`, `/collatz`,
`/userinfo`, `/ping`, `/status` (the lyric rotation in my status), `/help`, `/about`, `/invite`, `/source`

### 🔒 Owner (dev server only)
`/dashboard`, `/guildinfo`, `/leaveserver`, `/broadcast`, `/reload`, `/load`, `/unload`, `/cogs`, `/sync`, `/reloadlyrics`, `/shutdown`

---

## Project layout
```
main.py                 bot setup, command sync, global error handler, passive chat reactions
status.py               rotating lyric status
cogs/                   one file per feature (music, mod, automod, serverlog, flight, poker, ...)
functionality/
  store.py              JSON persistence in DATA_DIR
  modstore.py           cases, notes, guild config, log helpers
  aviation.py           flight / airport / weather API clients
  lyrics.py             LRCLIB lyrics lookup
  ui.py                 paginator, confirm buttons, duration parsing
lavalink/               Lavalink server config + Dockerfile (music backend)
docker-compose.yml      local Lavalink + bot
```

This was my first coding project, and it's continuously updated.
