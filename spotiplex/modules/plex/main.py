import datetime  # noqa: D100

import httpx
from loguru import logger
from plexapi.audio import Track
from plexapi.exceptions import BadRequest, NotFound
from plexapi.playlist import Playlist  # Typing
from plexapi.server import PlexServer
from plexapi.library import LibrarySection, MusicSection
from plexapi.audio import Track, Artist
import traceback
from fuzzywuzzy import fuzz

from spotiplex.config import Config
from spotiplex.modules.spotify.main import SpotifyPlaylist, SpotifyTrack


class PlexClass:
    """Class to contain Plex functions."""

    def __init__(self: "PlexClass") -> None:
        """Init for Plex class to set up variables and initiate connection."""
        self.plex_url = Config.PLEX_SERVER_URL
        self.plex_key = Config.PLEX_API_KEY
        self.replacement_policy = Config.PLEX_REPLACE
        self.plex : PlexServer = self.connect_plex()

    def connect_plex(self: "PlexClass") -> PlexServer:
        """Simple function to initiate Plex Server connection."""
        session = httpx.Client(verify=False)  # noqa: S501    Risk is acceptabl for me, feel free to require HTTPS, not a requirement of this app
        return PlexServer(self.plex_url, self.plex_key, session=session)

    # TODO: Add possibility to map Spotify IDs to Plex tracks
    def match_spotify_tracks_in_plex(
        self: "PlexClass",
        spotify_tracks: list[SpotifyTrack],
    ) -> list[Track]:
        """Match Spotify tracks in Plex library and provide a summary of the import."""
        logger.debug("Checking tracks in plex...")
        matched_tracks: list[Track] = []
        missing_tracks:list[SpotifyTrack] = []
        total_tracks = len(spotify_tracks)
        
        # TODO: this could be a list of libraries and the track search could
        #       iterate over all the possible sources
        music_library : MusicSection = self.plex.library.section(Config.PLEX_LIBRARY_NAME)

        for track in spotify_tracks:
            # TODO: Add alternative searches
            artists_in_plex : list[Artist] = self.find_all_possible_artists(music_library=music_library,artists=track.artists)
            if not artists_in_plex:
                logger.debug(f"No results found for artist: {track.artists[0]}")
                missing_tracks.append(track)
                continue

            # Try exact title match
            try:
                logger.debug(artists_in_plex)
                plex_track = self.find_first_matching_track(artists_in_plex=artists_in_plex, track_name=track.name)
            except NotFound:
                logger.debug(
                    f"Track '{track.name}' by '{track.artists[0]}' not found in Plex. (Other artist of the track: {track.artists[1:]})",
                )
                plex_track = None
            except (Exception, BadRequest) as plex_search_exception:
                logger.debug(
                    f"Exception trying to search for artist '{track.artists[0]}', track '{track.name}': {plex_search_exception}",
                )
                logger.debug(traceback.format_exc())
                plex_track = None

            # Try full search
            if not plex_track:
                title_matches : list[Track] = music_library.searchTracks(title=track.name, maxresults=15,)
                plex_track = self.match_artist_in_tracks(track.artists,title_matches)

            # Try search based on album name and track number
            # TODO

            if not plex_track:
                logger.debug("Song not in Plex!")
                logger.debug(
                    f"Found artists for '{track.artists[0]}' ({len(artists_in_plex)})",
                )
                logger.debug(f"Attempted to match song '{track.name}', but could not!")
                # TODO: send missing tracks to external service
                missing_tracks.append(track)

            else:
                matched_tracks.append(plex_track)

        success_percentage = (
            (len(matched_tracks) / total_tracks) * 100 if total_tracks else 0
        )
        logger.debug(
            f"We successfully found {len(matched_tracks)}/{len(spotify_tracks)} or {success_percentage:.2f}% of the tracks.",
        )
        logger.debug(f"We are missing these tracks: {missing_tracks}")
        return matched_tracks
    
    def find_first_matching_track(self: "PlexClass", artists_in_plex : list[Artist], track_name : str) -> Track | None :
        for artist in artists_in_plex:
            track = artist.track(title=track_name)
            if track:
                return track
        return None
    
    def find_all_possible_artists(self: "PlexClass", music_library : LibrarySection, artists : list[str]) -> list[Artist]:
        results = []
        for artist in artists:
            results.extend(music_library.search(title=artist))

        return results
    
    def match_artist_in_tracks(self : "PlexClass", artists : list[str], tracks : list[Track]) -> Track | None:
        for track in tracks:
            plex_artists : list[Artist] = (
						[track.artist()]
						if hasattr(track, "artist")
						else getattr(track, "artists", [])
					) #type: ignore
            for artist in artists:
                for plex_artist in plex_artists:
                    if hasattr(plex_artist,"title"):
                        plex_artist_name=plex_artist.title
                    else:
                        logger.debug(f"Plex artist has no attribute \"Title\" {plex_artist}")
                        continue
                    split_artists=plex_artist_name.split(";")
                    if len(split_artists) > 1:
                        logger.debug(f"Split the artist {plex_artist_name} up into {len(split_artists)} pieces")
                        for split_artist in split_artists:
                            split_match = self.match_artists(artist,split_artist)
                            if split_match:
                                return track
                    match = self.match_artists(artist,plex_artist_name)
                    if match:
                        return track

    def match_artists(self: "PlexClass", a : str, b : str) -> bool :
        ratio = fuzz.ratio(a,b) > 80
        logger.debug(f"The match between {a} and {b} was {ratio}")
        return ratio
        

    def set_cover_art(self: "PlexClass", playlist: Playlist, cover_url: str) -> None:
        """Sets cover art."""
        if cover_url is not None:
            try:
                playlist.uploadPoster(url=cover_url)
            except Exception as e:
                logger.error(
                    f"Couldn't set playlist cover for {playlist}, {cover_url}.",
                )
                logger.error(
                    f"Exception was {traceback.format_exc()}",
                )

    def create_playlist(
        self: "PlexClass",
        playlist: SpotifyPlaylist,
        tracks: list[Track],
    ) -> Playlist | None:
        """Create a playlist in Plex with the given tracks."""
        try:
            iteration_tracks = tracks[:300]
            del tracks[:300]  # Delete should be lower impact than slicing

            new_playlist: Playlist = self.plex.createPlaylist(
                playlist.name,
                items=iteration_tracks,
            )
            new_playlist.editSummary(
                summary=playlist.summary
            )
            if playlist.cover_url is not None:
                self.set_cover_art(new_playlist, playlist.cover_url)

            while tracks:
                iteration_tracks = tracks[:300]
                del tracks[:300]  # Delete should be lower impact than slicing
                new_playlist.addItems(iteration_tracks)

        except Exception as e:
            logger.debug(f"Error creating playlist {playlist.name}: {traceback.format_exc()}")

        else:
            return new_playlist

    def update_playlist(
        self: "PlexClass",
        existing_playlist: Playlist,
        playlist: SpotifyPlaylist,
        tracks: list,
    ) -> Playlist | None:
        """Update an existing playlist in Plex."""
        if self.replacement_policy is not None and self.replacement_policy is not False:
            existing_playlist.delete()
            return self.create_playlist(
                playlist,
                tracks,
            )
        else:
            logger.info(f"Skipped overwrite of playlist with name \"{existing_playlist}\" because of replacement policy")
        existing_playlist.editSummary(
            summary=playlist.summary,
        )
        if len(tracks) > 0:
            existing_playlist.addItems(tracks)
        return existing_playlist

    def find_playlist_by_name(self: "PlexClass", playlist_name: str) -> Playlist | None:
        """Find a playlist by name in Plex."""
        return next(
            (
                playlist
                for playlist in self.plex.playlists()
                if playlist and playlist_name in playlist.title
            ),
            None,
        )

    def create_or_update_playlist(
        self: "PlexClass",
        playlist: SpotifyPlaylist,
        tracks: list,
    ) -> Playlist | None:
        """Create or update a playlist in Plex."""
        existing_playlist = self.find_playlist_by_name(playlist.name)
        if existing_playlist is not None and tracks:
            return self.update_playlist(
                existing_playlist,
                playlist,
                tracks,
            )
        if tracks:
            return self.create_playlist(playlist, tracks)
        return None
