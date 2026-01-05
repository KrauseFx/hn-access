# hn-access

Minimal CLI to fetch Hacker News top stories from the official HN Firebase API.

## Why API (not scraping)

Hacker News provides an official Firebase API with endpoints for top stories and
item details. Using the API is simpler, more stable than HTML scraping, and
returns the fields needed for a digest (title, URL, score, comments, etc.).

## Usage

```bash
python3 hn_access.py --limit 25 --hours 24
```

Output formats:

```bash
# JSON (default)
python3 hn_access.py

# JSONL (one story per line)
python3 hn_access.py --format jsonl

# Human-readable text
python3 hn_access.py --format text
```

Tuning:

```bash
python3 hn_access.py --scan 300 --batch-size 30 --max-workers 12
```

## Output fields (JSON)

- `title`, `url`, `hn_url`, `comments_url`
- `score`, `descendants`, `kids_count`
- `by`, `time`, `time_iso`, `type`, `rank`

Example (JSONL):

```json
{"id": 123, "rank": 1, "title": "...", "url": "...", "hn_url": "...", "comments_url": "...", "score": 42, "by": "alice", "time": 1700000000, "time_iso": "2024-11-14T12:00:00+00:00", "descendants": 12, "kids_count": 12, "type": "story"}
```

## Agent-friendly workflow

The intended agent flow is:

1. Fetch data: `python3 hn_access.py --limit 25 --hours 24 --format json`
2. Create a digest from `items` (sorted by HN rank already)
3. Send email using your preferred mail provider or SMTP

## Notes

- Ask HN / Show HN posts may not have an external `url`; in that case `url` falls back to `hn_url`.
- Filtering is done by story timestamp within the last N hours, while preserving the top-stories ranking.
- The CLI scans the first `--scan` IDs in the list to find enough recent stories.
