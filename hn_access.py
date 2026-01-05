#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional

BASE_URL = "https://hacker-news.firebaseio.com/v0"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
DEFAULT_STORY_LIST = "topstories"


def _fetch_json(url: str, timeout: float, retries: int, user_agent: str) -> Any:
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as exc:  # pragma: no cover - minimal CLI retry logic
            last_err = exc
            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _get_story_ids(list_name: str, timeout: float, retries: int, user_agent: str) -> List[int]:
    url = f"{BASE_URL}/{list_name}.json"
    data = _fetch_json(url, timeout, retries, user_agent)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response for {list_name}: {data}")
    return [int(x) for x in data]


def _get_item(item_id: int, timeout: float, retries: int, user_agent: str) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/item/{item_id}.json"
    data = _fetch_json(url, timeout, retries, user_agent)
    if not isinstance(data, dict):
        return None
    return data


def _item_to_output(item: Dict[str, Any], rank: int) -> Dict[str, Any]:
    item_id = item.get("id")
    hn_url = HN_ITEM_URL.format(id=item_id)
    item_url = item.get("url") or hn_url
    ts = item.get("time")
    time_iso = None
    if isinstance(ts, int):
        time_iso = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()

    return {
        "id": item_id,
        "rank": rank,
        "title": item.get("title"),
        "url": item_url,
        "hn_url": hn_url,
        "comments_url": hn_url,
        "score": item.get("score"),
        "by": item.get("by"),
        "time": ts,
        "time_iso": time_iso,
        "descendants": item.get("descendants"),
        "kids_count": len(item.get("kids", []) or []),
        "type": item.get("type"),
    }


def _iter_batches(items: List[int], batch_size: int) -> Iterable[List[int]]:
    for idx in range(0, len(items), batch_size):
        yield items[idx : idx + batch_size]


def _collect_top_stories(
    story_ids: List[int],
    *,
    limit: int,
    hours: int,
    batch_size: int,
    max_workers: int,
    timeout: float,
    retries: int,
    user_agent: str,
) -> List[Dict[str, Any]]:
    cutoff = int(time.time()) - (hours * 3600)
    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch in _iter_batches(story_ids, batch_size):
            futures = {
                executor.submit(_get_item, item_id, timeout, retries, user_agent): item_id
                for item_id in batch
            }
            for future in as_completed(futures):
                item = future.result()
                if not item:
                    continue
                if item.get("deleted") or item.get("dead"):
                    continue
                if item.get("type") != "story":
                    continue
                item_time = item.get("time")
                if not isinstance(item_time, int) or item_time < cutoff:
                    continue
                results.append(item)
            if len(results) >= limit:
                break

    # Preserve original top-stories ordering by sorting on rank within the initial list.
    rank_index = {item_id: idx + 1 for idx, item_id in enumerate(story_ids)}
    results.sort(key=lambda item: rank_index.get(item.get("id"), 10**9))
    trimmed = results[:limit]
    return [
        _item_to_output(item, rank=rank_index.get(item.get("id"), 0))
        for item in trimmed
    ]


def _format_text(items: List[Dict[str, Any]]) -> str:
    lines = []
    for item in items:
        lines.append(f"{item['rank']}. {item['title']} ({item['score']} points)")
        lines.append(f"   {item['url']}")
        lines.append(f"   {item['comments_url']}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Hacker News top stories within the last N hours."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of stories to return (default: 25).",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Only include stories from the last N hours (default: 24).",
    )
    parser.add_argument(
        "--list",
        dest="story_list",
        default=DEFAULT_STORY_LIST,
        choices=["topstories", "newstories", "beststories"],
        help="Which HN list to use (default: topstories).",
    )
    parser.add_argument(
        "--scan",
        type=int,
        default=200,
        help="How many IDs from the list to scan (default: 200).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="How many items to fetch in parallel per batch (default: 25).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Max parallel item fetches (default: 10).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Request timeout in seconds (default: 10).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retry count for network errors (default: 2).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "jsonl", "text"],
        default="json",
        help="Output format (default: json).",
    )
    parser.add_argument(
        "--user-agent",
        default="hn-access/1.0",
        help="User-Agent header value (default: hn-access/1.0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    story_ids = _get_story_ids(args.story_list, args.timeout, args.retries, args.user_agent)
    if args.scan:
        story_ids = story_ids[: args.scan]

    items = _collect_top_stories(
        story_ids,
        limit=args.limit,
        hours=args.hours,
        batch_size=args.batch_size,
        max_workers=args.max_workers,
        timeout=args.timeout,
        retries=args.retries,
        user_agent=args.user_agent,
    )

    payload = {
        "generated_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "story_list": args.story_list,
        "limit": args.limit,
        "hours": args.hours,
        "count": len(items),
        "items": items,
    }

    if args.format == "json":
        json.dump(payload, sys.stdout, ensure_ascii=True, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.format == "jsonl":
        for item in items:
            json.dump(item, sys.stdout, ensure_ascii=True)
            sys.stdout.write("\n")
        return 0

    sys.stdout.write(_format_text(items) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
