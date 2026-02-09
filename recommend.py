#!/usr/bin/env python3
"""
Spotify Playlist Recommender

Takes an input Spotify playlist and creates a new playlist with song
recommendations based on co-occurrence in public playlists. Songs that
frequently appear alongside your favorites in other people's playlists
are likely good recommendations.

Usage:
    python recommend.py <playlist_url_or_id> [--name "My Recommendations"] [--count 30] [--search-limit 10]

Requires SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET environment variables
(or a .env file). Get these from https://developer.spotify.com/dashboard.
"""

import argparse
import os
import random
import sys
from collections import Counter

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

SCOPES = "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private"
REDIRECT_URI = "http://127.0.0.1:8080"


def authenticate():
    """Authenticate with Spotify using OAuth2 Authorization Code flow."""
    load_dotenv()

    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Error: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set.")
        print("Set them in a .env file or as environment variables.")
        print("Get credentials at: https://developer.spotify.com/dashboard")
        sys.exit(1)

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
    ))
    return sp


def extract_playlist_id(playlist_input):
    """Extract a playlist ID from a URL or URI, or return as-is if already an ID."""
    # Handle full URLs like https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
    if "open.spotify.com/playlist/" in playlist_input:
        path = playlist_input.split("open.spotify.com/playlist/")[1]
        return path.split("?")[0].split("/")[0]
    # Handle Spotify URIs like spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
    if playlist_input.startswith("spotify:playlist:"):
        return playlist_input.split("spotify:playlist:")[1]
    # Assume it's already a plain ID
    return playlist_input.strip()


def get_playlist_tracks(sp, playlist_id):
    """Fetch all tracks from a playlist, handling pagination."""
    tracks = []
    results = sp.playlist_tracks(playlist_id)

    while results:
        for item in results["items"]:
            track = item.get("track")
            if track and track.get("id"):
                tracks.append({
                    "id": track["id"],
                    "uri": track["uri"],
                    "name": track["name"],
                    "artists": [a["name"] for a in track.get("artists", [])],
                })
        results = sp.next(results) if results.get("next") else None

    return tracks


def search_public_playlists(sp, track, limit=5):
    """Search for public playlists that contain a given track."""
    query = f"{track['name']} {track['artists'][0]}"
    try:
        results = sp.search(q=query, type="playlist", limit=limit)
        return [p["id"] for p in results["playlists"]["items"] if p]
    except spotipy.SpotifyException:
        return []


def find_recommendations(sp, input_tracks, search_limit, progress=True):
    """
    Find recommended songs by analyzing co-occurrence in public playlists.

    Samples tracks from the input playlist, searches for public playlists
    containing those tracks, then counts how often each *other* song appears
    across all discovered playlists.
    """
    input_track_ids = {t["id"] for t in input_tracks}

    # Sample tracks to search with (avoid hitting rate limits on large playlists)
    sample_size = min(search_limit, len(input_tracks))
    sampled_tracks = random.sample(input_tracks, sample_size)

    candidate_counts = Counter()
    candidate_info = {}
    seen_playlists = set()

    for i, track in enumerate(sampled_tracks):
        if progress:
            print(f"  Searching playlists for track {i + 1}/{sample_size}: "
                  f"{track['name']} - {', '.join(track['artists'])}")

        playlist_ids = search_public_playlists(sp, track)

        for pid in playlist_ids:
            if pid in seen_playlists:
                continue
            seen_playlists.add(pid)

            try:
                pl_tracks = get_playlist_tracks(sp, pid)
            except spotipy.SpotifyException:
                continue

            for t in pl_tracks:
                if t["id"] not in input_track_ids:
                    candidate_counts[t["id"]] += 1
                    candidate_info[t["id"]] = t

    return candidate_counts, candidate_info


def create_playlist(sp, name, track_uris, description=""):
    """Create a new playlist and add tracks to it."""
    user_id = sp.current_user()["id"]
    playlist = sp.user_playlist_create(
        user_id,
        name,
        public=True,
        description=description,
    )

    # Spotify API allows adding max 100 tracks per request
    for i in range(0, len(track_uris), 100):
        sp.playlist_add_items(playlist["id"], track_uris[i:i + 100])

    return playlist


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Spotify playlist of recommendations based on an input playlist."
    )
    parser.add_argument(
        "playlist",
        help="Spotify playlist URL, URI, or ID",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Name for the output playlist (default: 'Recommendations from <input playlist>')",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=30,
        help="Number of recommendations to include (default: 30)",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=10,
        help="Number of input tracks to sample for searching (default: 10)",
    )
    args = parser.parse_args()

    print("Authenticating with Spotify...")
    sp = authenticate()

    playlist_id = extract_playlist_id(args.playlist)

    print(f"Fetching tracks from input playlist...")
    input_tracks = get_playlist_tracks(sp, playlist_id)
    if not input_tracks:
        print("Error: No tracks found in the input playlist.")
        sys.exit(1)
    print(f"  Found {len(input_tracks)} tracks.")

    # Get input playlist name for default output name
    playlist_info = sp.playlist(playlist_id, fields="name")
    input_playlist_name = playlist_info["name"]

    print(f"\nSearching for public playlists containing your songs...")
    candidate_counts, candidate_info = find_recommendations(
        sp, input_tracks, args.search_limit
    )

    if not candidate_counts:
        print("Error: Could not find any recommendations. Try increasing --search-limit.")
        sys.exit(1)

    # Take the top N most frequently co-occurring songs
    top_recommendations = candidate_counts.most_common(args.count)
    rec_uris = [candidate_info[track_id]["uri"] for track_id, _ in top_recommendations]

    print(f"\nTop {len(top_recommendations)} recommendations:")
    for rank, (track_id, count) in enumerate(top_recommendations, 1):
        info = candidate_info[track_id]
        print(f"  {rank:3d}. {info['name']} - {', '.join(info['artists'])} (appeared in {count} playlists)")

    output_name = args.name or f"Recommendations from {input_playlist_name}"
    description = (
        f"Auto-generated recommendations based on '{input_playlist_name}'. "
        f"Songs that frequently appear alongside your favorites in public playlists."
    )

    print(f"\nCreating playlist: {output_name}")
    playlist = create_playlist(sp, output_name, rec_uris, description=description)
    print(f"Done! Playlist created: {playlist['external_urls']['spotify']}")


if __name__ == "__main__":
    main()
