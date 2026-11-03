#!/usr/bin/env python3
"""Generate an SVG summary of a GitHub user's public and accessible activity."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

API_URL = "https://api.github.com/graphql"
USERNAME = os.environ.get("GITHUB_USERNAME", "jgermade")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
OUTPUT = Path(__file__).resolve().parents[1] / "github-stats.svg"
COLORS = ["#e5a982", "#f1df58", "#ed4b26", "#53639b", "#347fc4", "#00b7d5"]

QUERY = """
query($login: String!, $cursor: String, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name
    login
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def graphql(login: str, from_date: str, to_date: str, cursor: str | None) -> dict:
    payload = json.dumps({
        "query": QUERY,
        "variables": {"login": login, "from": from_date, "to": to_date, "cursor": cursor},
    }).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-stats-generator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {error.code}: {detail}") from error
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")
    return result["data"]["user"]


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def text(x: int, y: int, value: object, size: int = 17, color: str = "#a9fff5", weight: int = 600) -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(value)}</text>'


def rect(x: int, y: int, width: int, height: int) -> str:
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#151321" stroke="#dedde5" stroke-width="1.5"/>'


def current_and_longest_streak(days: list[dict], today: dt.date) -> tuple[int, int]:
    counts = {dt.date.fromisoformat(day["date"]): day["contributionCount"] for day in days}
    longest = run = 0
    previous = None
    for day in sorted(counts):
        run = run + 1 if counts[day] > 0 and previous == day - dt.timedelta(days=1) else (1 if counts[day] > 0 else 0)
        longest = max(longest, run)
        previous = day

    end = today if counts.get(today, 0) else today - dt.timedelta(days=1)
    current = 0
    while counts.get(end - dt.timedelta(days=current), 0) > 0:
        current += 1
    return current, longest


def make_svg(user: dict, year: int, contributions: int, commits: int, prs: int, issues: int,
             stars: int, current: int, longest: int, languages: dict[str, int]) -> str:
    display_name = user.get("name") or user["login"]
    top_languages = sorted(languages.items(), key=lambda item: item[1], reverse=True)[:6]
    total_bytes = sum(size for _, size in top_languages) or 1
    markup = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500" viewBox="0 0 1000 500">',
        '<rect width="1000" height="500" rx="18" fill="#0d1117"/>',
        '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI, sans-serif">',
        rect(20, 20, 600, 235), rect(640, 20, 340, 235), rect(20, 275, 960, 205),
        text(45, 62, f"{display_name}'s GitHub Stats", 27, "#ff3e91", 700),
    ]
    metrics = [
        ("Total Stars Earned", stars), (f"Total Commits ({year})", commits),
        ("Total PRs", prs), ("Total Issues", issues), ("Contributions (last year)", contributions),
    ]
    for index, (label, value) in enumerate(metrics):
        y = 100 + index * 31
        markup.extend([text(48, y, "✦", 21, "#f1df58", 700), text(78, y, f"{label}:", 17),
                       text(400, y, f"{value:,}", 18, "#a9fff5", 700)])

    markup.extend([text(670, 68, "Most Used Languages", 23, "#ff3e91", 700)])
    bar_x, bar_y, bar_width = 670, 91, 280
    if top_languages:
        offset = 0
        for index, (name, size) in enumerate(top_languages):
            width = bar_width * size / total_bytes
            markup.append(f'<rect x="{bar_x + offset:.1f}" y="{bar_y}" width="{width:.1f}" height="12" fill="{COLORS[index % len(COLORS)]}"/>')
            offset += width
        for index, (name, size) in enumerate(top_languages):
            column_x = 670 + (index % 2) * 145
            row_y = 137 + (index // 2) * 32
            percentage = size * 100 / total_bytes
            markup.extend([
                f'<circle cx="{column_x + 6}" cy="{row_y - 5}" r="6" fill="{COLORS[index % len(COLORS)]}"/>',
                text(column_x + 18, row_y, f"{name} {percentage:.1f}%", 13),
            ])
    else:
        markup.append(text(670, 135, "No language data available", 14))

    markup.extend([
        text(95, 335, f"{contributions:,}", 38, "#a9fff5", 700),
        text(75, 370, "Contributions in the last year", 17),
        text(420, 335, str(current), 38, "#ffab00", 700),
        text(385, 370, "Current streak (days)", 17),
        text(740, 335, str(longest), 38, "#a9fff5", 700),
        text(700, 370, "Longest streak (days)", 17),
        text(75, 430, f"Updated daily · @{user['login']}", 14, "#a9fff5", 400),
        "</g></svg>",
    ])
    return "\n".join(markup) + "\n"


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set GITHUB_TOKEN or GH_TOKEN to a GitHub token with read access.")
    today = dt.datetime.now(dt.timezone.utc).date()
    year_start = dt.date(today.year, 1, 1)
    from_date = (today - dt.timedelta(days=364)).isoformat() + "T00:00:00Z"
    to_date = (today + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"

    user = None
    cursor = None
    stars = 0
    language_totals: defaultdict[str, int] = defaultdict(int)
    while True:
        user = graphql(USERNAME, from_date, to_date, cursor)
        repositories = user["repositories"]
        for repository in repositories["nodes"]:
            stars += repository["stargazerCount"]
            for edge in repository["languages"]["edges"]:
                language_totals[edge["node"]["name"]] += edge["size"]
        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    collection = user["contributionsCollection"]
    days = [day for week in collection["contributionCalendar"]["weeks"] for day in week["contributionDays"]]
    current, longest = current_and_longest_streak(days, today)
    recent_contributions = sum(
        day["contributionCount"] for day in days
        if today - dt.timedelta(days=364) <= dt.date.fromisoformat(day["date"]) <= today
    )
    svg = make_svg(
        user, year_start.year, recent_contributions, collection["totalCommitContributions"],
        collection["totalPullRequestContributions"], collection["totalIssueContributions"],
        stars, current, longest, dict(language_totals),
    )
    OUTPUT.write_text(svg, encoding="utf-8")
    print(f"Updated {OUTPUT}")


if __name__ == "__main__":
    main()
