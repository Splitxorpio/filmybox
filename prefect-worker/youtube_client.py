from datetime import date

import httpx

YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"

# search.list costs 100 quota units against a 10,000/day free quota - only
# ever called for movies not yet post_release (see stage_scan.py), never the
# full historical corpus (4,395 x 100 would be ~44x the daily quota).
_client = httpx.Client(base_url=YOUTUBE_BASE_URL, timeout=15.0)


class YouTubeQuotaExceeded(Exception):
    pass


def _get(path: str, params: dict) -> dict:
    resp = _client.get(path, params=params)
    if resp.status_code == 403 and "quota" in resp.text.lower():
        raise YouTubeQuotaExceeded()
    resp.raise_for_status()
    return resp.json()


def search_trailer(title: str, year: int | None, api_key: str) -> dict | None:
    """One search.list call (100 units). Returns the top result as
    {"video_id", "title", "published_at"}, or None if nothing came back.
    """
    query = f"{title} {year} official trailer" if year else f"{title} official trailer"
    data = _get(
        "/search",
        {"part": "snippet", "q": query, "type": "video", "maxResults": 1, "key": api_key},
    )
    items = data.get("items", [])
    if not items:
        return None

    item = items[0]
    published_at = item["snippet"]["publishedAt"]
    return {
        "video_id": item["id"]["videoId"],
        "title": item["snippet"]["title"],
        "published_at": date.fromisoformat(published_at[:10]),
    }


def get_top_level_comments(video_id: str, api_key: str, max_results: int = 100) -> list[dict]:
    """One commentThreads.list call (1 unit - far cheaper than search.list's
    100). Returns top-level comments only (no reply-thread traversal, v1
    scope) as [{"id", "text", "engagement"}, ...]. Comments disabled on the
    video is a real, expected case (not every trailer allows them) - returns
    [] rather than raising, same style as search_trailer's None-on-nothing.
    """
    try:
        data = _get(
            "/commentThreads",
            {"part": "snippet", "videoId": video_id, "maxResults": min(max_results, 100), "key": api_key},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return []
        raise

    comments = []
    for item in data.get("items", []):
        top = item["snippet"]["topLevelComment"]["snippet"]
        comments.append(
            {
                "id": item["id"],
                "text": top.get("textDisplay", ""),
                "engagement": top.get("likeCount", 0),
            }
        )
    return comments


def get_video_stats(video_ids: list[str], api_key: str) -> dict[str, dict]:
    """One videos.list call per <=50 ids (~1 unit each). Returns
    {video_id: {"view_count", "like_count", "comment_count"}}.
    """
    if not video_ids:
        return {}

    stats_by_id = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        data = _get("/videos", {"part": "statistics", "id": ",".join(batch), "key": api_key})
        for item in data.get("items", []):
            stats = item.get("statistics", {})
            stats_by_id[item["id"]] = {
                "view_count": int(stats["viewCount"]) if "viewCount" in stats else None,
                "like_count": int(stats["likeCount"]) if "likeCount" in stats else None,
                "comment_count": int(stats["commentCount"]) if "commentCount" in stats else None,
            }
    return stats_by_id
