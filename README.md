# TrackForge

A self-hosted music request and acquisition platform. Think Jellyseerr, but for music — and without the Lidarr dependency. Users can search for artists and albums via MusicBrainz, request tracks or full albums, and have them automatically acquired and organized into your media library.

## Features

- **Search & Browse** — Live artist/album/track search powered by MusicBrainz
- **Request System** — Users request songs or albums; admins approve and track fulfillment
- **Acquisition Pipeline** — Automated download via Usenet (Prowlarr + NZBGet/SABnzbd), Soulseek (slskd), or torrents (qBittorrent)
- **Library Management** — Configurable folder/file naming patterns, auto-import into your music library
- **Song Previews** — 30-second previews via Spotify or iTunes, with YouTube fallback
- **Jellyfin Integration** — Optional library scan triggers after import
- **Discord Notifications** — Webhook alerts for request status changes
- **Multi-user** — Registration, admin approval, role-based access

---

## Required Services

| Service | Purpose | Notes |
|---------|---------|-------|
| **PostgreSQL** | Primary database | Included in Docker Compose (postgres:16-alpine) |
| **Redis** | Search cache & task queue | Included in Docker Compose (redis:7-alpine) |

## Required APIs

| API | Purpose | Auth |
|-----|---------|------|
| **MusicBrainz** | Artist, album, and track metadata | Free — requires a contact email (`MUSICBRAINZ_CONTACT`) |

## Optional APIs

| API | Purpose | Auth |
|-----|---------|------|
| **Spotify** | Song preview playback (primary) | Client credentials — `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` ([developer.spotify.com](https://developer.spotify.com)) |
| **Fanart.tv** | Artist background/thumbnail images | API key — `FANART_API_KEY` ([fanart.tv](https://fanart.tv)) |
| **AcoustID** | Audio fingerprint matching for imports | API key — `ACOUSTID_API_KEY` ([acoustid.org](https://acoustid.org)) |
| **Discogs** | Supplemental metadata | Personal token — `DISCOGS_TOKEN` |

## Optional Services

| Service | Purpose | Config |
|---------|---------|--------|
| **Prowlarr** | Usenet/torrent indexer aggregation | `PROWLARR_URL`, `PROWLARR_API_KEY` |
| **NZBGet** | Usenet downloader | `NZBGET_URL`, `NZBGET_USERNAME`, `NZBGET_PASSWORD` |
| **SABnzbd** | Usenet downloader (alternative) | `SABNZBD_URL`, `SABNZBD_API_KEY` |
| **slskd** | Soulseek client | `SLSKD_URL`, `SLSKD_API_KEY` |
| **qBittorrent** | Torrent client | `QBITTORRENT_URL`, `QBITTORRENT_USERNAME`, `QBITTORRENT_PASSWORD` |
| **Jellyfin** | Media server (library scan on import) | `JELLYFIN_URL`, `JELLYFIN_API_KEY` |
| **Discord** | Webhook notifications | `DISCORD_WEBHOOK_URL` |

---

## Deployment

### Prerequisites

- Docker and Docker Compose
- A directory structure for media and staging data (bind-mounted into containers)
- An external Docker network if running alongside other media services (e.g., Jellyfin)

### Directory Layout

```
/opt/trackforge/            # Application root
/data/trackforge/staging/   # Temporary staging area for imports
/data/media/music/          # Final music library
/data/downloads/complete/music/  # NZBGet completed downloads (worker only)
```

### Quick Start

1. **Clone the repo:**
   ```bash
   git clone https://github.com/Costellos/TrackForge.git /opt/trackforge
   cd /opt/trackforge
   ```

2. **Create the external network** (if it doesn't exist):
   ```bash
   docker network create media-server_media
   ```

3. **Create your `.env` file:**
   ```bash
   cp .env.example .env   # or create manually
   ```

   Minimum required variables:
   ```env
   POSTGRES_PASSWORD=your-secure-password
   SECRET_KEY=your-secret-key
   MUSICBRAINZ_CONTACT=your-email@example.com
   ```

4. **Start the stack:**
   ```bash
   docker compose up -d --build
   ```

5. **Access the UI** at `http://your-server:8612`

### Services Overview

| Container | Role | Port |
|-----------|------|------|
| `web` | Nginx serving React frontend + reverse proxy to API | **8612** (host) → 80 (container) |
| `api` | FastAPI backend | Internal only (proxied by `web`) |
| `worker` | ARQ background task worker | No ports |
| `db` | PostgreSQL 16 | Internal only |
| `redis` | Redis 7 | Internal only |

### Networking

The Compose stack joins an external network called `media-server_media`. This allows cross-compose communication with services like Jellyfin, Prowlarr, NZBGet, and slskd running in other Compose stacks. If you don't need this, remove the `media` network from `docker-compose.yml`.

### Updating

```bash
cd /opt/trackforge
git pull
docker compose up -d --build
```

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy (async), Alembic
- **Frontend:** React, TypeScript, Vite
- **Database:** PostgreSQL
- **Queue/Cache:** Redis, ARQ
- **Deployment:** Docker Compose, Nginx

## License

See [LICENSE](LICENSE) for details.
