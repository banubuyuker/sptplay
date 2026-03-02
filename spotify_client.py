"""
Spotify API client and authentication handling.
"""

import base64
import os
from typing import Optional
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

load_dotenv()

# Spotify API endpoints
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# Load credentials from environment
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/auth/callback")

# Scopes needed for playlist management
SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-read-private",
]


class SpotifyClient:
    """Client for interacting with Spotify API."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an async request to Spotify API."""
        async with httpx.AsyncClient() as client:
            url = f"{SPOTIFY_API_BASE}{endpoint}"
            response = await client.request(method, url, headers=self.headers, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}

    async def get_current_user(self) -> dict:
        """Get current user's profile."""
        return await self._request("GET", "/me")

    async def get_playlists(self, limit: int = 50, offset: int = 0) -> dict:
        """Get current user's playlists."""
        return await self._request(
            "GET", "/me/playlists", params={"limit": limit, "offset": offset}
        )

    async def get_all_playlists(self) -> list:
        """Get all playlists (handles pagination)."""
        playlists = []
        offset = 0
        limit = 50

        while True:
            response = await self.get_playlists(limit=limit, offset=offset)
            playlists.extend(response.get("items", []))

            if response.get("next") is None:
                break
            offset += limit

        return playlists

    async def get_playlist(self, playlist_id: str) -> dict:
        """Get a specific playlist."""
        return await self._request("GET", f"/playlists/{playlist_id}")

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 100, offset: int = 0
    ) -> dict:
        """Get tracks from a playlist."""
        return await self._request(
            "GET",
            f"/playlists/{playlist_id}/items",
            params={"limit": limit, "offset": offset},
        )

    async def get_all_playlist_tracks(self, playlist_id: str) -> list:
        """Get all tracks from a playlist (handles pagination)."""
        tracks = []
        offset = 0
        limit = 100

        while True:
            response = await self.get_playlist_tracks(
                playlist_id, limit=limit, offset=offset
            )
            tracks.extend(response.get("items", []))

            if response.get("next") is None:
                break
            offset += limit

        return tracks

    async def get_audio_features(self, track_ids: list[str]) -> dict:
        """Get audio features for multiple tracks (max 100)."""
        ids = ",".join(track_ids[:100])
        return await self._request("GET", "/audio-features", params={"ids": ids})

    async def create_playlist(
        self, name: str, description: str = "", public: bool = False
    ) -> dict:
        """Create a new playlist."""
        user = await self.get_current_user()
        user_id = user["id"]

        return await self._request(
            "POST",
            f"/users/{user_id}/playlists",
            json={"name": name, "description": description, "public": public},
        )

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_uris: list[str]
    ) -> dict:
        """Add tracks to a playlist (max 100 at a time)."""
        return await self._request(
            "POST", f"/playlists/{playlist_id}/items", json={"uris": track_uris[:100]}
        )

    async def update_playlist(
        self,
        playlist_id: str,
        name: str = None,
        description: str = None,
        public: bool = None,
    ) -> dict:
        """Update playlist details."""
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if public is not None:
            data["public"] = public

        return await self._request("PUT", f"/playlists/{playlist_id}", json=data)

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_uris: list[str]
    ) -> dict:
        """Remove tracks from a playlist."""
        tracks = [{"uri": uri} for uri in track_uris]
        return await self._request(
            "DELETE", f"/playlists/{playlist_id}/items", json={"tracks": tracks}
        )


def get_auth_url(state: Optional[str] = None) -> str:
    """Generate Spotify authorization URL."""
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    if state:
        params["state"] = state

    return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    """Exchange authorization code for access token."""
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        response.raise_for_status()
        return response.json()
        return response.json()
