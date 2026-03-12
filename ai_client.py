"""
AI Client for song information using OpenAI API.
Provides brief info about songs: genre, original version, and context.
"""

import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()


class AIClient:
    """Simple AI client for getting song information via OpenAI."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.enabled = bool(self.api_key)

    async def get_song_info(
        self, song_name: str, artist: str, album: str, year: str
    ) -> Optional[str]:
        """
        Get brief AI-generated info about a song.
        Returns a single line with genre, original version info if applicable.
        """
        if not self.enabled:
            return None

        url = "https://api.openai.com/v1/chat/completions"

        prompt = f"""For this song, provide a SINGLE LINE (max 100 chars) with:
- Genre (e.g., Soul, Rock, Folk)
- If it's a cover: "Cover of [original artist] ([year])"
- If it's a traditional/folk song: "Traditional/Folk"
- Any notable fact (optional, if space allows)

Song: "{song_name}"
Artist: {artist}
Album: {album}
Year: {year}

Reply with ONLY the single line info, no quotes, no explanation. Example formats:
- Soul/R&B - Original
- Rock - Cover of The Beatles (1965)
- Folk - Traditional Irish ballad
- Indie Rock - Original, debut single"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a music expert. Provide brief, accurate song info.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 60,
                        "temperature": 0.3,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()

        except httpx.TimeoutException:
            return "⏱️ AI timeout"
        except Exception:
            # Silently fail - AI info is optional
            return None


# Global instance
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get or create the global AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


async def get_song_ai_info(
    song_name: str, artist: str, album: str, year: str
) -> Optional[str]:
    """Convenience function to get song info."""
    client = get_ai_client()
    return await client.get_song_info(song_name, artist, album, year)
