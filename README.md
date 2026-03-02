# Spotify Playlist Organizer

A simple interactive tool to organize your Spotify liked songs into playlists.

## Features

- 🎵 Browse your liked songs one by one
- 📁 Add songs to existing playlists
- ➕ Create new playlists on the fly
- 🗑️ Remove songs from your liked collection
- 🔄 Automatic token refresh

## Setup

1. **Install dependencies:**

   This repository uses `uv` for dependency management. If you don't have uv:

   ```bash
   pip install uv
   ```

   Then install dependencies via:

   ```bash
   uv sync
   ```

2. **Create Spotify App:**
   - Go to https://developer.spotify.com/dashboard
   - Create a new app
   - Add redirect URI: `http://127.0.0.1:8000`
   - Copy Client ID and Client Secret

3. **Configure environment:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your Spotify credentials.

4. **Start the API server:**

   ```bash
   uvicorn main:app
   ```

5. **Authenticate:**
   - Open http://127.0.0.1:8000/auth/login
   - Authorize the app
   - Tokens will be auto-saved to `.env`

6. **Run the organizer:**

   ```bash
   python organize.py
   ```

## Usage

Navigate through your liked songs using:
- `S` - Skip to next song
- `R` - Remove from liked songs
- `N` - Create new playlist and add song
- `1-15` - Add to numbered playlist
- `M` - Show more playlists
- `Q` - Quit

## API Endpoints

- `GET /` - API info
- `GET /auth/login` - Start OAuth flow
- `GET /auth/callback` - OAuth callback
- `GET /playlists` - List user playlists (requires auth)