"""
Spotify Playlist Organizer API
A FastAPI application to manage and organize your Spotify playlists.
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from routes import playlists, auth

app = FastAPI(
    title="Spotify Playlist Organizer",
    description="API to organize, manage, and analyze your Spotify playlists",
    version="1.0.0"
)

# CORS middleware (useful if you ever add a frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(playlists.router, prefix="/playlists", tags=["Playlists"])


@app.get("/")
async def root(code: str = Query(None), error: str = Query(None)):
    """Welcome endpoint with API overview. Also handles OAuth callback if redirect URI is set to root."""
    # If there's an auth code, redirect to the callback handler
    if code or error:
        params = f"?code={code}" if code else f"?error={error}"
        return RedirectResponse(url=f"/auth/callback{params}")
    
    return {
        "message": "Spotify Playlist Organizer API",
        "docs": "/docs",
        "endpoints": {
            "auth": "/auth - Spotify authentication",
            "playlists": "/playlists - Playlist management"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
