"""
Playlist management routes.
Features: View, Create, Edit, Sort, Find Duplicates, Merge, Backup
"""

import json
from datetime import datetime
from typing import Optional, Literal
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

from spotify_client import SpotifyClient

router = APIRouter()


def get_spotify_client(authorization: str) -> SpotifyClient:
    """Extract token from Authorization header and create client."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, 
            detail="Missing or invalid Authorization header. Use: Bearer <access_token>"
        )
    token = authorization.replace("Bearer ", "")
    return SpotifyClient(token)


# ==================== PYDANTIC MODELS ====================

class CreatePlaylistRequest(BaseModel):
    name: str
    description: str = ""
    public: bool = False


class UpdatePlaylistRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    public: Optional[bool] = None


class AddTracksRequest(BaseModel):
    track_uris: list[str]  # Spotify URIs like "spotify:track:xxx"


class MergePlaylistsRequest(BaseModel):
    source_playlist_ids: list[str]
    new_playlist_name: str
    description: str = ""
    remove_duplicates: bool = True


# ==================== VIEW PLAYLISTS ====================

@router.get("/")
async def get_all_playlists(authorization: str = Header(...)):
    """
    Get all your playlists with basic info.
    """
    client = get_spotify_client(authorization)
    
    try:
        playlists = await client.get_all_playlists()
        
        return {
            "total": len(playlists),
            "playlists": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "description": p.get("description", ""),
                    "tracks_count": p["tracks"]["total"],
                    "public": p["public"],
                    "collaborative": p["collaborative"],
                    "owner": p["owner"]["display_name"],
                    "url": p["external_urls"]["spotify"]
                }
                for p in playlists
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playlist_id}")
async def get_playlist_details(playlist_id: str, authorization: str = Header(...)):
    """
    Get detailed info about a specific playlist including all tracks.
    """
    client = get_spotify_client(authorization)
    
    try:
        playlist = await client.get_playlist(playlist_id)
        tracks = await client.get_all_playlist_tracks(playlist_id)
        
        track_list = []
        for item in tracks:
            track = item.get("track")
            if track:
                track_list.append({
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "artists": [a["name"] for a in track.get("artists", [])],
                    "album": track.get("album", {}).get("name"),
                    "duration_ms": track.get("duration_ms"),
                    "uri": track.get("uri"),
                    "added_at": item.get("added_at"),
                    "added_by": item.get("added_by", {}).get("id")
                })
        
        return {
            "id": playlist["id"],
            "name": playlist["name"],
            "description": playlist.get("description", ""),
            "public": playlist["public"],
            "tracks_count": len(track_list),
            "tracks": track_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CREATE & EDIT PLAYLISTS ====================

@router.post("/")
async def create_playlist(request: CreatePlaylistRequest, authorization: str = Header(...)):
    """
    Create a new playlist.
    """
    client = get_spotify_client(authorization)
    
    try:
        playlist = await client.create_playlist(
            name=request.name,
            description=request.description,
            public=request.public
        )
        
        return {
            "message": "Playlist created successfully",
            "playlist": {
                "id": playlist["id"],
                "name": playlist["name"],
                "url": playlist["external_urls"]["spotify"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{playlist_id}")
async def update_playlist(
    playlist_id: str, 
    request: UpdatePlaylistRequest, 
    authorization: str = Header(...)
):
    """
    Update playlist name, description, or visibility.
    """
    client = get_spotify_client(authorization)
    
    try:
        await client.update_playlist(
            playlist_id=playlist_id,
            name=request.name,
            description=request.description,
            public=request.public
        )
        
        return {"message": "Playlist updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playlist_id}/tracks")
async def add_tracks(
    playlist_id: str, 
    request: AddTracksRequest, 
    authorization: str = Header(...)
):
    """
    Add tracks to a playlist.
    Track URIs should be in format: spotify:track:TRACK_ID
    """
    client = get_spotify_client(authorization)
    
    try:
        # Add tracks in batches of 100
        added = 0
        for i in range(0, len(request.track_uris), 100):
            batch = request.track_uris[i:i+100]
            await client.add_tracks_to_playlist(playlist_id, batch)
            added += len(batch)
        
        return {"message": f"Added {added} tracks to playlist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{playlist_id}/tracks")
async def remove_tracks(
    playlist_id: str, 
    request: AddTracksRequest, 
    authorization: str = Header(...)
):
    """
    Remove tracks from a playlist.
    """
    client = get_spotify_client(authorization)
    
    try:
        await client.remove_tracks_from_playlist(playlist_id, request.track_uris)
        return {"message": f"Removed {len(request.track_uris)} tracks from playlist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SORT TRACKS BY ATTRIBUTES ====================

@router.get("/{playlist_id}/sort")
async def sort_playlist_tracks(
    playlist_id: str,
    sort_by: Literal["tempo", "energy", "danceability", "valence", "acousticness", "duration", "name", "artist", "added_at"] = "tempo",
    order: Literal["asc", "desc"] = "desc",
    authorization: str = Header(...)
):
    """
    Get playlist tracks sorted by audio features or metadata.
    
    Audio features (from Spotify's analysis):
    - tempo: BPM (beats per minute)
    - energy: Intensity and activity (0.0 to 1.0)
    - danceability: How suitable for dancing (0.0 to 1.0)
    - valence: Musical positiveness/happiness (0.0 to 1.0)
    - acousticness: How acoustic the track is (0.0 to 1.0)
    
    Metadata:
    - duration: Track length
    - name: Track name (alphabetical)
    - artist: Artist name (alphabetical)
    - added_at: When track was added to playlist
    """
    client = get_spotify_client(authorization)
    
    try:
        tracks = await client.get_all_playlist_tracks(playlist_id)
        
        # Build track info list
        track_info = []
        track_ids = []
        
        for item in tracks:
            track = item.get("track")
            if track and track.get("id"):
                track_ids.append(track["id"])
                track_info.append({
                    "id": track["id"],
                    "name": track["name"],
                    "artists": [a["name"] for a in track.get("artists", [])],
                    "artist": track.get("artists", [{}])[0].get("name", ""),
                    "uri": track["uri"],
                    "duration_ms": track.get("duration_ms", 0),
                    "added_at": item.get("added_at", "")
                })
        
        # Get audio features if sorting by audio attribute
        audio_attrs = ["tempo", "energy", "danceability", "valence", "acousticness"]
        
        if sort_by in audio_attrs:
            # Get audio features in batches of 100
            features_map = {}
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i+100]
                features = await client.get_audio_features(batch)
                for f in features.get("audio_features", []):
                    if f:
                        features_map[f["id"]] = f
            
            # Add features to track info
            for track in track_info:
                f = features_map.get(track["id"], {})
                track["tempo"] = f.get("tempo", 0)
                track["energy"] = f.get("energy", 0)
                track["danceability"] = f.get("danceability", 0)
                track["valence"] = f.get("valence", 0)
                track["acousticness"] = f.get("acousticness", 0)
        
        # Sort tracks
        reverse = order == "desc"
        
        if sort_by == "duration":
            track_info.sort(key=lambda x: x["duration_ms"], reverse=reverse)
        elif sort_by == "name":
            track_info.sort(key=lambda x: x["name"].lower(), reverse=reverse)
        elif sort_by == "artist":
            track_info.sort(key=lambda x: x["artist"].lower(), reverse=reverse)
        elif sort_by == "added_at":
            track_info.sort(key=lambda x: x["added_at"], reverse=reverse)
        elif sort_by in audio_attrs:
            track_info.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
        
        return {
            "playlist_id": playlist_id,
            "sorted_by": sort_by,
            "order": order,
            "total_tracks": len(track_info),
            "tracks": track_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FIND DUPLICATES ====================

@router.get("/{playlist_id}/duplicates")
async def find_duplicates(playlist_id: str, authorization: str = Header(...)):
    """
    Find duplicate tracks in a playlist.
    Detects duplicates by:
    - Exact same track ID
    - Same track name + artist (different versions/releases)
    """
    client = get_spotify_client(authorization)
    
    try:
        tracks = await client.get_all_playlist_tracks(playlist_id)
        
        # Track by ID
        id_counts = defaultdict(list)
        # Track by name+artist
        name_artist_counts = defaultdict(list)
        
        for idx, item in enumerate(tracks):
            track = item.get("track")
            if track:
                track_id = track.get("id")
                track_name = track.get("name", "").lower()
                artist = track.get("artists", [{}])[0].get("name", "").lower()
                
                track_data = {
                    "position": idx,
                    "id": track_id,
                    "name": track.get("name"),
                    "artists": [a["name"] for a in track.get("artists", [])],
                    "album": track.get("album", {}).get("name"),
                    "uri": track.get("uri")
                }
                
                if track_id:
                    id_counts[track_id].append(track_data)
                
                key = f"{track_name}|{artist}"
                name_artist_counts[key].append(track_data)
        
        # Find exact duplicates (same ID)
        exact_duplicates = [
            {"track_id": tid, "occurrences": items}
            for tid, items in id_counts.items()
            if len(items) > 1
        ]
        
        # Find similar tracks (same name+artist but different ID)
        similar_tracks = []
        for key, items in name_artist_counts.items():
            unique_ids = set(item["id"] for item in items if item["id"])
            if len(unique_ids) > 1:
                similar_tracks.append({
                    "track_key": key,
                    "versions": items
                })
        
        return {
            "playlist_id": playlist_id,
            "exact_duplicates": {
                "count": len(exact_duplicates),
                "items": exact_duplicates
            },
            "similar_tracks": {
                "count": len(similar_tracks),
                "description": "Same song name + artist, but different track IDs (remixes, re-releases, etc.)",
                "items": similar_tracks
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{playlist_id}/duplicates")
async def remove_duplicates(
    playlist_id: str, 
    keep: Literal["first", "last"] = "first",
    authorization: str = Header(...)
):
    """
    Remove exact duplicate tracks from a playlist.
    - keep=first: Keep the first occurrence
    - keep=last: Keep the last occurrence
    """
    client = get_spotify_client(authorization)
    
    try:
        tracks = await client.get_all_playlist_tracks(playlist_id)
        
        # Find duplicates
        seen = {}
        duplicates_to_remove = []
        
        track_list = []
        for idx, item in enumerate(tracks):
            track = item.get("track")
            if track and track.get("id"):
                track_list.append({
                    "idx": idx,
                    "id": track["id"],
                    "uri": track["uri"]
                })
        
        if keep == "last":
            track_list.reverse()
        
        for track in track_list:
            if track["id"] in seen:
                duplicates_to_remove.append(track["uri"])
            else:
                seen[track["id"]] = True
        
        if duplicates_to_remove:
            # Remove in batches
            for i in range(0, len(duplicates_to_remove), 100):
                batch = duplicates_to_remove[i:i+100]
                await client.remove_tracks_from_playlist(playlist_id, batch)
        
        return {
            "message": f"Removed {len(duplicates_to_remove)} duplicate tracks",
            "removed_uris": duplicates_to_remove
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MERGE PLAYLISTS ====================

@router.post("/merge")
async def merge_playlists(request: MergePlaylistsRequest, authorization: str = Header(...)):
    """
    Merge multiple playlists into a new playlist.
    Optionally removes duplicate tracks.
    """
    client = get_spotify_client(authorization)
    
    try:
        # Create new playlist
        new_playlist = await client.create_playlist(
            name=request.new_playlist_name,
            description=request.description or f"Merged from {len(request.source_playlist_ids)} playlists"
        )
        new_playlist_id = new_playlist["id"]
        
        # Collect all track URIs
        all_uris = []
        seen_uris = set()
        
        for source_id in request.source_playlist_ids:
            tracks = await client.get_all_playlist_tracks(source_id)
            
            for item in tracks:
                track = item.get("track")
                if track and track.get("uri"):
                    uri = track["uri"]
                    
                    if request.remove_duplicates:
                        if uri not in seen_uris:
                            all_uris.append(uri)
                            seen_uris.add(uri)
                    else:
                        all_uris.append(uri)
        
        # Add tracks to new playlist in batches
        for i in range(0, len(all_uris), 100):
            batch = all_uris[i:i+100]
            await client.add_tracks_to_playlist(new_playlist_id, batch)
        
        return {
            "message": "Playlists merged successfully",
            "new_playlist": {
                "id": new_playlist_id,
                "name": request.new_playlist_name,
                "url": new_playlist["external_urls"]["spotify"]
            },
            "total_tracks": len(all_uris),
            "duplicates_removed": len(seen_uris) if request.remove_duplicates else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== BACKUP PLAYLISTS ====================

@router.get("/backup/all")
async def backup_all_playlists(authorization: str = Header(...)):
    """
    Export all playlists to a JSON backup.
    Returns data that can be saved to a file.
    """
    client = get_spotify_client(authorization)
    
    try:
        user = await client.get_current_user()
        playlists = await client.get_all_playlists()
        
        backup_data = {
            "backup_date": datetime.utcnow().isoformat(),
            "user": {
                "id": user["id"],
                "display_name": user.get("display_name")
            },
            "playlists": []
        }
        
        for playlist in playlists:
            tracks = await client.get_all_playlist_tracks(playlist["id"])
            
            track_list = []
            for item in tracks:
                track = item.get("track")
                if track:
                    track_list.append({
                        "id": track.get("id"),
                        "name": track.get("name"),
                        "artists": [a["name"] for a in track.get("artists", [])],
                        "album": track.get("album", {}).get("name"),
                        "uri": track.get("uri"),
                        "added_at": item.get("added_at")
                    })
            
            backup_data["playlists"].append({
                "id": playlist["id"],
                "name": playlist["name"],
                "description": playlist.get("description", ""),
                "public": playlist["public"],
                "tracks": track_list
            })
        
        return backup_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playlist_id}/backup")
async def backup_playlist(playlist_id: str, authorization: str = Header(...)):
    """
    Export a single playlist to a JSON backup.
    """
    client = get_spotify_client(authorization)
    
    try:
        playlist = await client.get_playlist(playlist_id)
        tracks = await client.get_all_playlist_tracks(playlist_id)
        
        track_list = []
        for item in tracks:
            track = item.get("track")
            if track:
                track_list.append({
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "artists": [a["name"] for a in track.get("artists", [])],
                    "album": track.get("album", {}).get("name"),
                    "uri": track.get("uri"),
                    "added_at": item.get("added_at")
                })
        
        return {
            "backup_date": datetime.utcnow().isoformat(),
            "playlist": {
                "id": playlist["id"],
                "name": playlist["name"],
                "description": playlist.get("description", ""),
                "public": playlist["public"],
                "url": playlist["external_urls"]["spotify"],
                "tracks": track_list
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore")
async def restore_playlist(
    name: str = Query(..., description="Name for the restored playlist"),
    track_uris: list[str] = Query(..., description="List of track URIs to restore"),
    authorization: str = Header(...)
):
    """
    Restore a playlist from a backup.
    Provide the track URIs from a backup to create a new playlist.
    """
    client = get_spotify_client(authorization)
    
    try:
        # Create new playlist
        new_playlist = await client.create_playlist(
            name=name,
            description="Restored from backup"
        )
        
        # Add tracks in batches
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            await client.add_tracks_to_playlist(new_playlist["id"], batch)
        
        return {
            "message": "Playlist restored successfully",
            "playlist": {
                "id": new_playlist["id"],
                "name": name,
                "tracks_count": len(track_uris),
                "url": new_playlist["external_urls"]["spotify"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
