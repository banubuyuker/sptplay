"""
Spotify Organizer - Interactive tool to analyze and organize your music.
"""

import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SpotifyOrganizer:
    """Interactive Spotify music organizer."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make GET request to Spotify API."""
        async with httpx.AsyncClient() as client:
            url = f"{SPOTIFY_API_BASE}{endpoint}"
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_liked_songs(self, limit: int = None) -> list:
        """
        Get all liked/saved songs from your library.
        Returns list of tracks with details.
        """
        tracks = []
        offset = 0
        batch_size = 50

        print("Fetching your liked songs...")

        while True:
            response = await self._get(
                "/me/items", {"limit": batch_size, "offset": offset}
            )
            items = response.get("items", [])
            tracks.extend(items)

            print(f"  Fetched {len(tracks)} songs...")

            if limit and len(tracks) >= limit:
                tracks = tracks[:limit]
                break

            if response.get("next") is None:
                break
            offset += batch_size

        return tracks

    async def get_artist_details(self, artist_ids: list) -> dict:
        """Get artist details including genres (batch of max 50)."""
        if not artist_ids:
            return {}

        ids = ",".join(artist_ids[:50])
        response = await self._get("/artists", {"ids": ids})

        return {
            artist["id"]: artist for artist in response.get("artists", []) if artist
        }

    async def analyze_liked_songs(self, limit: int = None) -> list:
        """
        Analyze liked songs and return details including:
        - Song name
        - Artist
        - Genre (from artist)
        - Year (from album release date)
        - Language (inferred from market/artist origin when possible)
        """
        liked = await self.get_liked_songs(limit)

        # Collect unique artist IDs
        artist_ids = set()
        for item in liked:
            track = item.get("track", {})
            for artist in track.get("artists", []):
                if artist.get("id"):
                    artist_ids.add(artist["id"])

        # Fetch artist details in batches of 50
        print("Fetching artist details for genres...")
        artist_details = {}
        artist_id_list = list(artist_ids)

        for i in range(0, len(artist_id_list), 50):
            batch = artist_id_list[i : i + 50]
            details = await self.get_artist_details(batch)
            artist_details.update(details)

        # Build song analysis
        print("Analyzing songs...\n")
        analyzed_songs = []

        for item in liked:
            track = item.get("track", {})
            if not track:
                continue

            # Get artist genres
            genres = []
            artist_names = []
            for artist in track.get("artists", []):
                artist_names.append(artist.get("name", "Unknown"))
                artist_id = artist.get("id")
                if artist_id and artist_id in artist_details:
                    genres.extend(artist_details[artist_id].get("genres", []))

            # Get year from album release date
            album = track.get("album", {})
            release_date = album.get("release_date", "")
            year = release_date[:4] if release_date else "Unknown"

            # Note: Spotify doesn't provide language directly
            # We can only infer from available markets or leave it for manual tagging
            available_markets = track.get("available_markets", [])

            song_info = {
                "name": track.get("name", "Unknown"),
                "artists": artist_names,
                "album": album.get("name", "Unknown"),
                "year": year,
                "genres": list(set(genres)) if genres else ["Unknown"],
                "duration_ms": track.get("duration_ms", 0),
                "uri": track.get("uri"),
                "id": track.get("id"),
                "added_at": item.get("added_at"),
                "popularity": track.get("popularity", 0),
            }

            analyzed_songs.append(song_info)

        return analyzed_songs

    def display_songs(self, songs: list):
        """Display songs in a readable format."""
        print("=" * 80)
        print(f"{'SONG':<35} {'ARTIST':<20} {'YEAR':<6} {'GENRES'}")
        print("=" * 80)

        for song in songs:
            name = song["name"][:33] + ".." if len(song["name"]) > 35 else song["name"]
            artist = ", ".join(song["artists"])
            artist = artist[:18] + ".." if len(artist) > 20 else artist
            genres = ", ".join(song["genres"][:2])  # Show first 2 genres
            genres = genres[:30] + ".." if len(genres) > 32 else genres

            print(f"{name:<35} {artist:<20} {song['year']:<6} {genres}")

        print("=" * 80)
        print(f"Total: {len(songs)} songs")


async def main():
    """Main entry point."""
    # Get token from environment or prompt
    token = os.getenv("SPOTIFY_ACCESS_TOKEN")

    if not token:
        print("No SPOTIFY_ACCESS_TOKEN found in environment.")
        print("Please run the auth flow first or set your token.")
        print("\nTo get a token:")
        print("1. Run the FastAPI server: uvicorn main:app --reload")
        print("2. Visit: http://localhost:8000/auth/login")
        print("3. Copy the access_token and set it:")
        print("   export SPOTIFY_ACCESS_TOKEN='your_token_here'")
        return

    organizer = SpotifyOrganizer(token)

    # Analyze first 50 liked songs (you can change or remove the limit)
    songs = await organizer.analyze_liked_songs(limit=50)

    # Display results
    organizer.display_songs(songs)

    # Return the data for further processing
    return songs


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(main())
