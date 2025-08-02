from typing import Optional
import spotipy
from loguru import logger
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
import traceback

from spotiplex.config import Config

class SpotifyPlaylist:
    name:str
    summary:str
    cover_url:Optional[str]
    id:str

class SpotifyTrack:
    def __init__(self, id:str, artists:list[str], name:str, album:str, length:int):
        self.id:str = id
        self.artists:list[str]=artists
        self.name:str=name
        self.album:str=album
        self.length:int=length #in milliseconds

class SpotifyClass:
    """Class for interacting with Spotify."""

    def __init__(self: "SpotifyClass") -> None:
        """Init for Spotify class."""
        self.spotify_id = Config.SPOTIFY_API_ID
        self.spotify_key = Config.SPOTIFY_API_KEY
        self.sp:Spotify = self.connect_spotify()

    def connect_spotify(self: "SpotifyClass") -> Spotify:
        """Init of spotify connection."""
        auth_manager = SpotifyClientCredentials(
            client_id=self.spotify_id,
            client_secret=self.spotify_key,
        )
        return spotipy.Spotify(auth_manager=auth_manager)

    def get_playlist_tracks(
        self: "SpotifyClass",
        playlist_id: str,
    ) -> list[SpotifyTrack]:
        """Fetch tracks from a Spotify playlist."""
        tracks: list[SpotifyTrack] = []
        try:
            results = self.sp.playlist_items(playlist_id,additional_types=("track"))
            while results:
                tracks.extend(
                    [
                        SpotifyTrack(
                            id=item["track"]["id"],
                            artists=[
                                artist["name"]
                                for artist in item["track"]["artists"]
                            ],
                            name=item["track"]["name"],
                            album=item["track"]["album"]["name"],
                            length=item["track"]["duration_ms"]
                        )
                        for item in results["items"]
                    ],
                )
                results = self.sp.next(results) if results["next"] else None
        except Exception as e:
            logger.debug(f"Error fetching tracks from Spotify: {traceback.format_exc()}")
        return tracks
    
    def get_playlist_data(self: "SpotifyClass", playlist_id: str) -> Optional[SpotifyPlaylist]:
        """Tries to get different aspects of the playlist, returns None if not found"""
        try:
            playlist_data = self.sp.playlist(playlist_id)
        except Exception as e:
            logger.error(f"Error retrieving playlist data for playlist {playlist_id}: {e}")
            playlist_data = None
        result = SpotifyPlaylist()
        result.id = playlist_id
        if playlist_data:
            logger.debug(f"Spotify playlist data result: {playlist_data}")
            if "images" in playlist_data:
                result.cover_url = playlist_data["images"][0]["url"]
            if "name" in playlist_data:
                result.name = playlist_data["name"]
            else:
                logger.debug(
                    f"Playlist name could not be retrieved for playlist ID '{playlist_id}'.",
                )
                return None
            if "description" in playlist_data:
                result.summary = playlist_data["description"]
            else:
                result.summary = ""
        return result