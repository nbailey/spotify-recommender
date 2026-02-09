# spotify-recommender

Generate a Spotify playlist of new song recommendations based on your existing playlist. The script finds public playlists that contain songs from your input playlist, then recommends songs that frequently co-occur with your favorites.

## How it works

1. Reads all tracks from your input Spotify playlist
2. Samples tracks and searches for public playlists containing those songs
3. Counts how often each new song appears across the discovered playlists
4. Songs that appear most frequently alongside yours are the strongest recommendations
5. Creates a new playlist on your Spotify account with the top recommendations

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

# Search more input tracks for broader recommendations (default: 10)
python recommend.py <playlist_url> --search-limit 20
```

You can pass a playlist URL, a Spotify URI (`spotify:playlist:...`), or a plain playlist ID.

On first run, a browser window will open for Spotify login. The auth token is cached locally for subsequent runs.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | `Recommendations from <input playlist>` | Name of the output playlist |
| `--count` | `30` | Number of songs to recommend |
| `--search-limit` | `10` | Number of input tracks to sample when searching for public playlists |

## License

See [LICENSE](LICENSE).
