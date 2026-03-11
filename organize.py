"""
Interactive Spotify Song Organizer
Go through liked songs one by one and organize them into playlists.
"""

import asyncio
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class TokenManager:
    """Manages access token with automatic refresh."""

    def __init__(self):
        self.token = os.getenv("SPOTIFY_ACCESS_TOKEN")
        self.refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        expires_at_str = os.getenv("SPOTIFY_TOKEN_EXPIRES_AT", "") or "0"
        self.expires_at = float(expires_at_str) if expires_at_str else 0.0
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    async def ensure_valid(self):
        """Check if token is expired and refresh if needed."""
        if not self.token:
            raise ValueError("No SPOTIFY_ACCESS_TOKEN found in .env")

        # Check if token will expire in next 5 minutes
        if time.time() >= (self.expires_at - 300):
            if self.refresh_token:
                await self._refresh_token()
            else:
                print("⚠️ Token expired and no refresh token available.")
                print("Get a new token at: http://127.0.0.1:8000/auth/login")
                raise ValueError("Access token expired")

    async def _refresh_token(self):
        """Refresh the access token using refresh token."""
        import base64

        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient(trust_env=False) as client:
            try:
                response = await client.post(
                    "https://accounts.spotify.com/api/token",
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.refresh_token,
                    },
                )
                response.raise_for_status()
                token_data = response.json()

                # Update instance
                self.token = token_data["access_token"]
                self.expires_at = time.time() + token_data["expires_in"]
                if "refresh_token" in token_data:
                    self.refresh_token = token_data["refresh_token"]

                # Update .env file
                self._save_to_env()
                print(f"✅ Token refreshed (expires in {token_data['expires_in']}s)\n")

            except Exception as e:
                print(f"❌ Failed to refresh token: {e}")
                raise

    def _save_to_env(self):
        """Save token to .env file."""
        env_path = Path(".env")
        content = env_path.read_text()

        # Update each token field
        content = content.replace(
            f"SPOTIFY_ACCESS_TOKEN={os.getenv('SPOTIFY_ACCESS_TOKEN')}",
            f"SPOTIFY_ACCESS_TOKEN={self.token}",
        )
        content = content.replace(
            f"SPOTIFY_REFRESH_TOKEN={os.getenv('SPOTIFY_REFRESH_TOKEN')}",
            f"SPOTIFY_REFRESH_TOKEN={self.refresh_token}",
        )
        content = content.replace(
            f"SPOTIFY_TOKEN_EXPIRES_AT={os.getenv('SPOTIFY_TOKEN_EXPIRES_AT')}",
            f"SPOTIFY_TOKEN_EXPIRES_AT={self.expires_at}",
        )

        env_path.write_text(content)

        # Reload env
        load_dotenv(override=True)


class SpotifyOrganizer:
    def __init__(self, access_token: str, token_manager: TokenManager = None):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.playlists = []
        self.token_manager = token_manager

    async def _ensure_token(self):
        """Check and refresh token if needed."""
        if self.token_manager:
            await self.token_manager.ensure_valid()
            # Update headers with fresh token
            self.headers = {"Authorization": f"Bearer {self.token_manager.token}"}

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        await self._ensure_token()
        async with httpx.AsyncClient(trust_env=False) as client:
            try:
                response = await client.get(
                    f"{SPOTIFY_API_BASE}{endpoint}", headers=self.headers, params=params
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"Error in _get {endpoint}: {e}")
                if hasattr(e, "response") and hasattr(e.response, "text"):
                    print(f"Response text: {e.response.text}")
                raise

    async def _post(self, endpoint: str, json: dict = None) -> dict:
        await self._ensure_token()
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                f"{SPOTIFY_API_BASE}{endpoint}", headers=self.headers, json=json
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def _delete(self, endpoint: str, json_data: dict = None) -> dict:
        await self._ensure_token()
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.request(
                "DELETE",
                f"{SPOTIFY_API_BASE}{endpoint}",
                headers=self.headers,
                json=json_data,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

    async def _put(self, endpoint: str, json: dict = None) -> dict:
        await self._ensure_token()
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.put(
                f"{SPOTIFY_API_BASE}{endpoint}", headers=self.headers, json=json
            )
            response.raise_for_status()
            return {}

    async def get_playlists(self, writable_only: bool = True) -> list:
        """Fetch user playlists. If writable_only=True, only return playlists the user can modify."""
        playlists = []
        offset = 0

        # Get current user ID to check ownership
        user = await self._get("/me")
        user_id = user.get("id")

        while True:
            response = await self._get("/me/playlists", {"limit": 50, "offset": offset})
            items = response.get("items", [])

            if writable_only:
                # Only include playlists user owns or that are collaborative
                for playlist in items:
                    owner_id = playlist.get("owner", {}).get("id")
                    is_collaborative = playlist.get("collaborative", False)
                    if owner_id == user_id or is_collaborative:
                        playlists.append(playlist)
            else:
                playlists.extend(items)

            if response.get("next") is None:
                break
            offset += 50

        self.playlists = playlists
        return playlists

    async def get_liked_songs(self, limit: int = None) -> list:
        """Fetch liked songs."""
        tracks = []
        offset = 0

        while True:
            response = await self._get("/me/tracks", {"limit": 50, "offset": offset})
            tracks.extend(response.get("items", []))

            if limit and len(tracks) >= limit:
                return tracks[:limit]
            if response.get("next") is None:
                break
            offset += 50

        return tracks

    async def add_to_playlist(self, playlist_id: str, track_uri: str):
        """Add a track to a playlist."""
        await self._post(f"/playlists/{playlist_id}/items", {"uris": [track_uri]})

    async def remove_from_liked(self, track_id: str):
        """Remove a track from liked songs using the /me/library endpoint."""
        uri = f"spotify:track:{track_id}"
        await self._delete(f"/me/library?uris={uri}")

    async def create_playlist(self, name: str) -> dict:
        """Create a new playlist."""
        user = await self._get("/me")
        return await self._post(
            f"/users/{user['id']}/playlists", {"name": name, "public": False}
        )

    async def get_playlist_items(self, playlist_id: str, limit: int = None) -> list:
        """Fetch items from a playlist using the new API endpoint."""
        tracks = []
        offset = 0

        while True:
            response = await self._get(
                f"/playlists/{playlist_id}/items",
                {"limit": 50, "offset": offset, "additional_types": "track"},
            )
            items = response.get("items", [])
            tracks.extend(items)

            if limit and len(tracks) >= limit:
                return tracks[:limit]
            if response.get("next") is None:
                break
            offset += 50

        return tracks

    async def remove_from_playlist(self, playlist_id: str, track_uri: str):
        """Remove a track from a playlist."""
        await self._delete(
            f"/playlists/{playlist_id}/items",
            {"items": [{"uri": track_uri}]},
        )

    async def delete_playlist(self, playlist_id: str):
        """Unfollow/delete a playlist."""
        await self._delete(f"/playlists/{playlist_id}/followers")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def display_song(song: dict, index: int, total: int):
    """Display song info."""
    print("\n" + "=" * 60)
    print(f"  Song {index + 1} of {total}")
    print("=" * 60)
    print(f"\n  🎵 {song['name']}")
    print(f"  🎤 {', '.join(song['artists'])}")
    print(f"  💿 {song['album']}")
    print(f"  📅 {song['year']}")
    print("\n" + "-" * 60)


def display_menu(playlists: list, can_go_back: bool = False):
    """Display action menu for liked songs mode."""
    print("\nWhat do you want to do?\n")
    print("  [S] Skip to next song")
    if can_go_back:
        print("  [P] Previous song")
    print("  [R] Remove from liked songs")
    print("  [N] Create new playlist and add")
    print("  [A #] Add to playlist # (keep in liked)")
    print("  [Q] Quit")
    print("\n  -- Or move to playlist (removes from liked): --\n")

    for i, playlist in enumerate(playlists[:15], 1):  # Show first 15 playlists
        name = (
            playlist["name"][:40] + ".."
            if len(playlist["name"]) > 42
            else playlist["name"]
        )
        print(f"  [{i}] {name}")

    if len(playlists) > 15:
        print(f"\n  ... and {len(playlists) - 15} more playlists")
        print("  [M] Show more playlists")


def display_playlist_menu(
    playlists: list, source_playlist_name: str, can_go_back: bool = False
):
    """Display action menu for playlist organize mode."""
    print("\nWhat do you want to do?\n")
    print("  [S] Skip to next song")
    if can_go_back:
        print("  [P] Previous song")
    print(f"  [R] Remove from '{source_playlist_name}'")
    print("  [N] Create new playlist and move")
    print(f"  [A #] Add to playlist # (keep in '{source_playlist_name}')")
    print("  [Q] Quit")
    print(f"\n  -- Or move to playlist (removes from '{source_playlist_name}'): --\n")

    for i, playlist in enumerate(playlists[:15], 1):  # Show first 15 playlists
        name = (
            playlist["name"][:40] + ".."
            if len(playlist["name"]) > 42
            else playlist["name"]
        )
        print(f"  [{i}] {name}")

    if len(playlists) > 15:
        print(f"\n  ... and {len(playlists) - 15} more playlists")
        print("  [M] Show more playlists")


def display_main_menu():
    """Display main menu to choose mode."""
    print("\n🎵 Spotify Song Organizer")
    print("=" * 60)
    print("\nWhat would you like to organize?\n")
    print("  [1] Organize Liked Songs")
    print("  [2] Organize a Playlist")
    print("  [Q] Quit")
    print()


def display_playlist_selection(playlists: list):
    """Display playlist selection menu."""
    print("\n📋 Select a playlist to organize:\n")
    for i, playlist in enumerate(playlists, 1):
        name = (
            playlist["name"][:40] + ".."
            if len(playlist["name"]) > 42
            else playlist["name"]
        )
        print(f"  [{i}] {name}")
    print("\n  [Q] Back to main menu")
    print()


async def organize_liked_songs(organizer: SpotifyOrganizer, playlists: list):
    """Organize liked songs - go through each and move/add to playlists."""
    print("\nFetching liked songs...")
    liked_songs = await organizer.get_liked_songs()
    print(f"Found {len(liked_songs)} liked songs")

    # Build song list with details
    songs = []
    for item in liked_songs:
        track = item.get("track", {})
        if not track:
            continue

        album = track.get("album", {})
        release_date = album.get("release_date", "")

        songs.append(
            {
                "id": track.get("id"),
                "name": track.get("name", "Unknown"),
                "artists": [a.get("name", "Unknown") for a in track.get("artists", [])],
                "album": album.get("name", "Unknown"),
                "year": release_date[:4] if release_date else "Unknown",
                "uri": track.get("uri"),
            }
        )

    if not songs:
        print("\n📭 No liked songs to organize!")
        input("Press Enter to continue...")
        return

    print(f"\nReady! Let's organize {len(songs)} songs.\n")
    input("Press Enter to start...")

    # Main loop
    show_all_playlists = False
    i = 0

    while i < len(songs):
        song = songs[i]

        clear_screen()
        display_song(song, i, len(songs))

        if show_all_playlists:
            print("\n  All playlists:\n")
            for j, playlist in enumerate(playlists, 1):
                name = (
                    playlist["name"][:40] + ".."
                    if len(playlist["name"]) > 42
                    else playlist["name"]
                )
                print(f"  [{j}] {name}")
            print("\n  [B] Back to short list")
        else:
            display_menu(playlists, can_go_back=(i > 0))

        print()
        choice = input("Your choice: ").strip().upper()

        # Handle choice
        if choice == "Q":
            print("\n👋 Returning to main menu...")
            break

        elif choice == "S":
            i += 1
            continue

        elif choice == "P":
            if i > 0:
                i -= 1
            continue

        elif choice == "R":
            try:
                await organizer.remove_from_liked(song["id"])
                print(f"\n✅ Removed '{song['name']}' from liked songs")
                songs.pop(i)  # Remove from our list too
                input("Press Enter to continue...")
            except Exception as e:
                print(f"\n❌ Error: {e}")
                input("Press Enter to continue...")

        elif choice == "M":
            show_all_playlists = True

        elif choice == "B":
            show_all_playlists = False

        elif choice == "N":
            name = input("\nNew playlist name: ").strip()
            if name:
                try:
                    new_playlist = await organizer.create_playlist(name)
                    await organizer.add_to_playlist(new_playlist["id"], song["uri"])
                    playlists.insert(0, new_playlist)  # Add to beginning of list
                    print(f"\n✅ Created '{name}' and added '{song['name']}'")
                    i += 1
                    input("Press Enter to continue...")
                except Exception as e:
                    print(f"\n❌ Error: {e}")
                    input("Press Enter to continue...")

        elif choice.startswith("A") and len(choice) > 1:
            # A # = Add to playlist without removing from liked
            num_part = choice[1:].strip()
            if num_part.isdigit():
                idx = int(num_part) - 1
                if 0 <= idx < len(playlists):
                    try:
                        playlist = playlists[idx]
                        await organizer.add_to_playlist(playlist["id"], song["uri"])
                        print(
                            f"\n✅ Added '{song['name']}' to '{playlist['name']}' (kept in liked)"
                        )
                        i += 1
                        input("Press Enter to continue...")
                    except Exception as e:
                        print(f"\n❌ Error: {e}")
                        input("Press Enter to continue...")
                else:
                    print("\n❌ Invalid playlist number")
                    input("Press Enter to continue...")
            else:
                print("\n❌ Invalid format. Use: A 3 or A3")
                input("Press Enter to continue...")

        elif choice.isdigit():
            # Number = Move to playlist (add + remove from liked)
            idx = int(choice) - 1
            if 0 <= idx < len(playlists):
                try:
                    playlist = playlists[idx]
                    await organizer.add_to_playlist(playlist["id"], song["uri"])
                    await organizer.remove_from_liked(song["id"])
                    print(
                        f"\n✅ Moved '{song['name']}' to '{playlist['name']}' (removed from liked)"
                    )
                    songs.pop(i)  # Remove from our list too
                    input("Press Enter to continue...")
                except Exception as e:
                    print(f"\n❌ Error: {e}")
                    input("Press Enter to continue...")
            else:
                print("\n❌ Invalid playlist number")
                input("Press Enter to continue...")

        else:
            print("\n❌ Invalid choice")
            input("Press Enter to continue...")

    if i >= len(songs):
        print("\n🎉 All done! You've gone through all your liked songs.")
        input("Press Enter to continue...")


async def organize_playlist(
    organizer: SpotifyOrganizer, playlists: list, source_playlist: dict
):
    """Organize a specific playlist - go through each song and move/add to other playlists."""
    source_id = source_playlist["id"]
    source_name = source_playlist["name"]

    print(f"\nFetching songs from '{source_name}'...")
    playlist_items = await organizer.get_playlist_items(source_id)

    # Check if playlist is empty
    if not playlist_items:
        print(f"\n📭 '{source_name}' is empty!")
        choice = (
            input("Would you like to delete this playlist? [Y/N]: ").strip().upper()
        )
        if choice == "Y":
            try:
                await organizer.delete_playlist(source_id)
                print(f"\n✅ Deleted playlist '{source_name}'")
                # Remove from playlists list
                playlists[:] = [p for p in playlists if p["id"] != source_id]
            except Exception as e:
                print(f"\n❌ Error deleting playlist: {e}")
        input("Press Enter to continue...")
        return

    # Build song list with details
    songs = []
    for item in playlist_items:
        track = item.get("track") or item.get("item")  # API uses 'item' in new endpoint
        if not track or not track.get("id"):
            continue

        album = track.get("album", {})
        release_date = album.get("release_date", "")

        songs.append(
            {
                "id": track.get("id"),
                "name": track.get("name", "Unknown"),
                "artists": [a.get("name", "Unknown") for a in track.get("artists", [])],
                "album": album.get("name", "Unknown"),
                "year": release_date[:4] if release_date else "Unknown",
                "uri": track.get("uri"),
            }
        )

    if not songs:
        print(f"\n📭 No valid tracks found in '{source_name}'!")
        input("Press Enter to continue...")
        return

    print(f"Found {len(songs)} songs")
    print(f"\nReady! Let's organize '{source_name}'.\n")
    input("Press Enter to start...")

    # Filter out source playlist from target options
    target_playlists = [p for p in playlists if p["id"] != source_id]

    # Main loop
    show_all_playlists = False
    i = 0

    while i < len(songs):
        song = songs[i]

        clear_screen()
        print(f"\n📋 Organizing: {source_name}")
        display_song(song, i, len(songs))

        if show_all_playlists:
            print("\n  All playlists:\n")
            for j, playlist in enumerate(target_playlists, 1):
                name = (
                    playlist["name"][:40] + ".."
                    if len(playlist["name"]) > 42
                    else playlist["name"]
                )
                print(f"  [{j}] {name}")
            print("\n  [B] Back to short list")
        else:
            display_playlist_menu(target_playlists, source_name, can_go_back=(i > 0))

        print()
        choice = input("Your choice: ").strip().upper()

        # Handle choice
        if choice == "Q":
            print("\n👋 Returning to main menu...")
            break

        elif choice == "S":
            i += 1
            continue

        elif choice == "P":
            if i > 0:
                i -= 1
            continue

        elif choice == "R":
            try:
                await organizer.remove_from_playlist(source_id, song["uri"])
                print(f"\n✅ Removed '{song['name']}' from '{source_name}'")
                songs.pop(i)  # Remove from our list too
                input("Press Enter to continue...")
            except Exception as e:
                print(f"\n❌ Error: {e}")
                input("Press Enter to continue...")

        elif choice == "M":
            show_all_playlists = True

        elif choice == "B":
            show_all_playlists = False

        elif choice == "N":
            name = input("\nNew playlist name: ").strip()
            if name:
                try:
                    new_playlist = await organizer.create_playlist(name)
                    await organizer.add_to_playlist(new_playlist["id"], song["uri"])
                    await organizer.remove_from_playlist(source_id, song["uri"])
                    playlists.insert(0, new_playlist)  # Add to beginning of list
                    target_playlists.insert(0, new_playlist)
                    print(f"\n✅ Created '{name}' and moved '{song['name']}'")
                    songs.pop(i)
                    input("Press Enter to continue...")
                except Exception as e:
                    print(f"\n❌ Error: {e}")
                    input("Press Enter to continue...")

        elif choice.startswith("A") and len(choice) > 1:
            # A # = Add to playlist without removing from source
            num_part = choice[1:].strip()
            if num_part.isdigit():
                idx = int(num_part) - 1
                if 0 <= idx < len(target_playlists):
                    try:
                        playlist = target_playlists[idx]
                        await organizer.add_to_playlist(playlist["id"], song["uri"])
                        print(
                            f"\n✅ Added '{song['name']}' to '{playlist['name']}' (kept in '{source_name}')"
                        )
                        i += 1
                        input("Press Enter to continue...")
                    except Exception as e:
                        print(f"\n❌ Error: {e}")
                        input("Press Enter to continue...")
                else:
                    print("\n❌ Invalid playlist number")
                    input("Press Enter to continue...")
            else:
                print("\n❌ Invalid format. Use: A 3 or A3")
                input("Press Enter to continue...")

        elif choice.isdigit():
            # Number = Move to playlist (add + remove from source)
            idx = int(choice) - 1
            if 0 <= idx < len(target_playlists):
                try:
                    playlist = target_playlists[idx]
                    await organizer.add_to_playlist(playlist["id"], song["uri"])
                    await organizer.remove_from_playlist(source_id, song["uri"])
                    print(
                        f"\n✅ Moved '{song['name']}' to '{playlist['name']}' (removed from '{source_name}')"
                    )
                    songs.pop(i)  # Remove from our list too
                    input("Press Enter to continue...")
                except Exception as e:
                    print(f"\n❌ Error: {e}")
                    input("Press Enter to continue...")
            else:
                print("\n❌ Invalid playlist number")
                input("Press Enter to continue...")

        else:
            print("\n❌ Invalid choice")
            input("Press Enter to continue...")

    if i >= len(songs):
        print(f"\n🎉 All done! You've gone through all songs in '{source_name}'.")
        input("Press Enter to continue...")


async def interactive_organize():
    """Main interactive loop with mode selection."""
    token = os.getenv("SPOTIFY_ACCESS_TOKEN")

    if not token:
        print("\n❌ No SPOTIFY_ACCESS_TOKEN found!")
        print("\nTo get a token:")
        print("1. Run: uvicorn main:app --reload")
        print("2. Visit: http://127.0.0.1:8000/auth/login")
        print("3. Copy the access_token to your .env file")
        return

    # Create token manager for automatic refresh
    token_manager = TokenManager()
    organizer = SpotifyOrganizer(token, token_manager=token_manager)

    print("\n🎵 Spotify Song Organizer")
    print("=" * 60)

    # Fetch playlists
    print("\nFetching your playlists...")
    playlists = await organizer.get_playlists()
    print(f"Found {len(playlists)} playlists")

    # Main menu loop
    while True:
        clear_screen()
        display_main_menu()

        choice = input("Your choice: ").strip().upper()

        if choice == "Q":
            print("\n👋 Goodbye!")
            break

        elif choice == "1":
            await organize_liked_songs(organizer, playlists)

        elif choice == "2":
            # Playlist selection
            while True:
                clear_screen()
                display_playlist_selection(playlists)

                pl_choice = input("Select playlist number: ").strip().upper()

                if pl_choice == "Q":
                    break

                if pl_choice.isdigit():
                    idx = int(pl_choice) - 1
                    if 0 <= idx < len(playlists):
                        await organize_playlist(organizer, playlists, playlists[idx])
                        # Refresh playlists after organizing (in case any were deleted)
                        playlists = await organizer.get_playlists()
                        break
                    else:
                        print("\n❌ Invalid playlist number")
                        input("Press Enter to continue...")
                else:
                    print("\n❌ Invalid choice")
                    input("Press Enter to continue...")

        else:
            print("\n❌ Invalid choice")
            input("Press Enter to continue...")


if __name__ == "__main__":
    try:
        asyncio.run(interactive_organize())
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Goodbye!")
