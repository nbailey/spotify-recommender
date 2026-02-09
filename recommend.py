#!/usr/bin/env python3
"""
Spotify Playlist Recommender

Takes an input Spotify playlist and creates a new playlist with song
recommendations based on co-occurrence in public playlists. Songs that
frequently appear alongside your favorites in other people's playlists
are likely good recommendations.

Usage:
    python recommend.py <playlist_url_or_id> [--name "My Recommendations"] [--count 30]

Requires SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET environment variables
(or a .env file). Get these from https://developer.spotify.com/dashboard.
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

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


def discover_playlists(sp, input_tracks, search_results_per_track=5):
    """
    Phase 1: Broad search to discover candidate playlists.

    Searches for public playlists for every input track, collecting only
    playlist IDs. Counts how many different input track searches each
    playlist appeared in (the "hit count"). This is a cheap proxy for
    overlap before we commit to fetching full track lists.

    Returns a dict mapping playlist_id -> hit_count, sorted descending.
    """
    hit_counts = Counter()
    total = len(input_tracks)

    for i, track in enumerate(input_tracks):
        print(f"  [{i + 1}/{total}] Searching: "
              f"{track['name']} - {', '.join(track['artists'])}")
        playlist_ids = search_public_playlists(sp, track, limit=search_results_per_track)
        # Count each playlist at most once per input track search
        for pid in set(playlist_ids):
            hit_counts[pid] += 1

    return hit_counts


def score_playlist(input_track_ids, input_artist_by_track, playlist_tracks):
    """
    Score a playlist by how well it overlaps with the input playlist.

    Uses an exponential artist-diversity formula:
        score = matching_tracks * (distinct_matching_artists ^ 2)

    This heavily rewards playlists that share songs from many different
    artists rather than many songs from a single artist.
    """
    matching_artists = set()
    matching_count = 0

    for track in playlist_tracks:
        if track["id"] in input_track_ids:
            matching_count += 1
            artist = input_artist_by_track.get(track["id"])
            if artist:
                matching_artists.add(artist)

    if matching_count == 0:
        return 0, matching_count, len(matching_artists)

    score = matching_count * (len(matching_artists) ** 2)
    return score, matching_count, len(matching_artists)


def find_recommendations(sp, input_tracks, fetch_limit=50,
                         search_results_per_track=5):
    """
    Find recommended songs using a two-phase approach:

    Phase 1 - Discovery (cheap): Search for every input track to find
    public playlists. Track how many different input-track searches each
    playlist appears in ("hit count"). Playlists with higher hit counts
    likely share more songs with the input playlist.

    Phase 2 - Evaluation (selective): Fetch full track lists only for the
    top playlists ranked by hit count (up to fetch_limit). Compute a
    precise overlap score using the exponential artist-diversity formula:
        score = matching_tracks * (distinct_matching_artists ^ 2)
    Weight each candidate song by the score of the playlist it came from.
    """
    input_track_ids = {t["id"] for t in input_tracks}
    # Map track ID -> primary artist name for diversity scoring
    input_artist_by_track = {t["id"]: t["artists"][0] for t in input_tracks}

    # Phase 1: Discover candidate playlists with cheap search calls
    print("\nPhase 1: Discovering candidate playlists...")
    hit_counts = discover_playlists(sp, input_tracks, search_results_per_track)

    if not hit_counts:
        return Counter(), {}

    print(f"\n  Found {len(hit_counts)} unique playlists.")
    top_hit = hit_counts.most_common(1)[0][1]
    print(f"  Best candidate appeared in {top_hit} track searches.")

    # Phase 2: Fetch and score the top candidate playlists
    top_playlists = hit_counts.most_common(fetch_limit)
    print(f"\nPhase 2: Evaluating top {len(top_playlists)} playlists...")

    candidate_scores = defaultdict(float)
    candidate_info = {}

    for i, (pid, hits) in enumerate(top_playlists):
        print(f"  [{i + 1}/{len(top_playlists)}] Fetching playlist (hit count: {hits})...",
              end="", flush=True)

        try:
            pl_tracks = get_playlist_tracks(sp, pid)
        except spotipy.SpotifyException:
            print(" skipped (error)")
            continue

        score, match_count, artist_count = score_playlist(
            input_track_ids, input_artist_by_track, pl_tracks
        )

        print(f" {len(pl_tracks)} tracks, "
              f"{match_count} matches across {artist_count} artists, "
              f"score={score}")

        if score == 0:
            continue

        for t in pl_tracks:
            if t["id"] not in input_track_ids:
                candidate_scores[t["id"]] += score
                candidate_info[t["id"]] = t

    # Convert to Counter for .most_common() support
    return Counter(candidate_scores), candidate_info


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
        "--fetch-limit",
        type=int,
        default=50,
        help="Max number of candidate playlists to fully evaluate (default: 50)",
    )
    parser.add_argument(
        "--search-results-per-track",
        type=int,
        default=5,
        help="Number of playlist results per track search (default: 5)",
    )
    args = parser.parse_args()

    print("Authenticating with Spotify...")
    sp = authenticate()

    playlist_id = extract_playlist_id(args.playlist)

    print("Fetching tracks from input playlist...")
    input_tracks = get_playlist_tracks(sp, playlist_id)
    if not input_tracks:
        print("Error: No tracks found in the input playlist.")
        sys.exit(1)
    print(f"  Found {len(input_tracks)} tracks.")

    # Get input playlist name for default output name
    playlist_info = sp.playlist(playlist_id, fields="name")
    input_playlist_name = playlist_info["name"]

    candidate_scores, candidate_info = find_recommendations(
        sp, input_tracks,
        fetch_limit=args.fetch_limit,
        search_results_per_track=args.search_results_per_track,
    )

    if not candidate_scores:
        print("\nError: Could not find any recommendations. Try increasing --fetch-limit.")
        sys.exit(1)

    # Take the top N highest-scored songs
    top_recommendations = candidate_scores.most_common(args.count)
    rec_uris = [candidate_info[track_id]["uri"] for track_id, _ in top_recommendations]

    print(f"\nTop {len(top_recommendations)} recommendations:")
    for rank, (track_id, score) in enumerate(top_recommendations, 1):
        info = candidate_info[track_id]
        print(f"  {rank:3d}. {info['name']} - {', '.join(info['artists'])} "
              f"(score: {score:.0f})")

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
