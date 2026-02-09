# spotify-recommender

Generate a Spotify playlist of new song recommendations based on your existing playlist. The script finds public playlists that contain songs from your input playlist, then recommends songs that frequently co-occur with your favorites.

## How it works

The script uses a two-phase approach to find playlists with strong overlap before evaluating them:

1. **Discovery phase**: Searches Spotify for public playlists containing each track from your input playlist. Tracks how many of your different songs each public playlist appeared in search results for — playlists that show up across many searches likely share multiple songs with yours.
2. **Evaluation phase**: Fetches the full track lists of only the top candidate playlists (ranked by how many search hits they had). Computes a precise overlap score that rewards artist diversity: `score = matching_tracks * (distinct_matching_artists ^ 2)`. A playlist matching 4 of your songs from 3 different artists scores much higher than one matching 4 songs from a single artist.
3. **Scoring**: Each candidate song accumulates score from every evaluated playlist it appears in. Songs that consistently appear in high-overlap, artist-diverse playlists rise to the top.
4. **Popularity filter**: Excludes overly popular songs (Spotify popularity score > 80 by default) so recommendations surface lesser-known tracks you're less likely to have already heard.
5. **Output**: Creates a new playlist on your account with the top-scored recommendations.

## Setup

### 1. Create Spotify API credentials

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new application
3. Set the redirect URI to `http://127.0.0.1:8080`
4. Note your **Client ID** and **Client Secret**

### 2. Configure credentials

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Client ID and Client Secret.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Basic usage with a playlist URL
python recommend.py https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M

# Customize the output playlist name
python recommend.py <playlist_url> --name "My Discovery Mix"

# Change the number of recommendations (default: 30)
python recommend.py <playlist_url> --count 50

# Evaluate more candidate playlists for broader recommendations
python recommend.py <playlist_url> --fetch-limit 100

# Get more search results per track during discovery
python recommend.py <playlist_url> --search-results-per-track 30

# Include popular mainstream hits (disabled by default at 80)
python recommend.py <playlist_url> --max-popularity 100
```

You can pass a playlist URL, a Spotify URI (`spotify:playlist:...`), or a plain playlist ID.

On first run, a browser window will open for Spotify login. The auth token is cached locally for subsequent runs.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | `Recommendations from <input playlist>` | Name of the output playlist |
| `--count` | `30` | Number of songs to recommend |
| `--fetch-limit` | `50` | Max number of candidate playlists to fully evaluate in phase 2 |
| `--search-results-per-track` | `20` | Number of playlist results to collect per track search in phase 1 |
| `--max-popularity` | `80` | Exclude songs with Spotify popularity above this (0-100). Set to 100 to disable |

## License

See [LICENSE](LICENSE).
