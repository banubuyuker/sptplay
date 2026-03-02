"""
Authentication routes for Spotify OAuth flow.
"""

import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

from spotify_client import get_auth_url, exchange_code_for_token, refresh_access_token

load_dotenv()
router = APIRouter()

# In-memory token storage (use a proper database in production!)
token_storage = {}


@router.get("/login")
async def login():
    """
    Start Spotify OAuth flow.
    Redirects to Spotify's authorization page.
    """
    auth_url = get_auth_url()
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(code: str = Query(None), error: str = Query(None)):
    """
    OAuth callback endpoint.
    Spotify redirects here after user authorizes the app.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {error}")
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")
    
    try:
        import time
        from pathlib import Path
        
        token_data = await exchange_code_for_token(code)
        
        # Store tokens (in production, associate with user session)
        token_storage["access_token"] = token_data["access_token"]
        token_storage["refresh_token"] = token_data.get("refresh_token")
        token_storage["expires_in"] = token_data["expires_in"]
        
        # Also save to .env file for CLI usage
        try:
            env_path = Path(".env")
            if env_path.exists():
                content = env_path.read_text()
                expires_at = time.time() + token_data["expires_in"]
                
                content = content.replace(
                    f"SPOTIFY_ACCESS_TOKEN={os.getenv('SPOTIFY_ACCESS_TOKEN', '')}",
                    f"SPOTIFY_ACCESS_TOKEN={token_data['access_token']}"
                )
                content = content.replace(
                    f"SPOTIFY_REFRESH_TOKEN={os.getenv('SPOTIFY_REFRESH_TOKEN', '')}",
                    f"SPOTIFY_REFRESH_TOKEN={token_data.get('refresh_token', '')}"
                )
                content = content.replace(
                    f"SPOTIFY_TOKEN_EXPIRES_AT={os.getenv('SPOTIFY_TOKEN_EXPIRES_AT', '')}",
                    f"SPOTIFY_TOKEN_EXPIRES_AT={expires_at}"
                )
                env_path.write_text(content)
        except Exception as e:
            print(f"Warning: Could not save to .env: {e}")
        
        return {
            "message": "Successfully authenticated!",
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "expires_in": token_data["expires_in"],
            "token_type": token_data["token_type"],
            "hint": "Use this access_token in the Authorization header for API calls"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")


@router.post("/refresh")
async def refresh(refresh_token: str = Query(...)):
    """
    Refresh an expired access token.
    """
    try:
        token_data = await refresh_access_token(refresh_token)
        
        # Update stored token
        token_storage["access_token"] = token_data["access_token"]
        if "refresh_token" in token_data:
            token_storage["refresh_token"] = token_data["refresh_token"]
        
        return {
            "access_token": token_data["access_token"],
            "expires_in": token_data["expires_in"],
            "token_type": token_data["token_type"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}")


@router.get("/token")
async def get_stored_token():
    """
    Get the currently stored access token (for development/testing).
    """
    if "access_token" not in token_storage:
        raise HTTPException(status_code=401, detail="No token stored. Please login first at /auth/login")
    
    return {
        "access_token": token_storage["access_token"],
        "has_refresh_token": "refresh_token" in token_storage
    }
