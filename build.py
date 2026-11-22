#!/usr/bin/env python3
"""Build the One Minute Interview Tips static site from posts/*.md."""

from __future__ import annotations

import datetime as dt
import html
import re
import base64
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

SITE_NAME = "One Minute Interview Tips"
JOIN_URL = "https://www.skool.com/jobseekers"
JOIN_NAV = "Join the community"
JOIN_CTA = "Join the Job Seekers community"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise ValueError("Post is missing front matter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Post front matter is not closed")
    meta: dict[str, str] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid front matter line: {raw_line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value
    return meta, parts[2].strip()


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def format_date(value: dt.date) -> str:
    return value.strftime("%B %-d, %Y")


def load_posts() -> list[dict]:
    posts = []
    paths = sorted(POSTS_DIR.glob("*.md"))
    if not paths:
        raise SystemExit("No posts found in posts/")
    slugs = set()
    for path in paths:
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        for field in ("title", "slug", "date", "summary"):
            if not meta.get(field):
                raise SystemExit(f"{path.name} is missing '{field}'")
        slug = meta["slug"]
        if not SLUG_RE.match(slug):
            raise SystemExit(f"{path.name} has an invalid slug: {slug}")
        if slug in slugs:
            raise SystemExit(f"Duplicate slug: {slug}")
        slugs.add(slug)
        try:
            date = parse_date(meta["date"])
        except ValueError:
            raise SystemExit(f"{path.name} has an invalid date: {meta['date']}")
        image = meta.get("image", "").strip() or None
        if image and "/" in image:
            raise SystemExit(f"{path.name} image should be a file name only")
        if image and not any((STATIC_DIR / "images" / n).is_file() for n in (image, image + ".b64")):
            raise SystemExit(f"{path.name} image not found: static/images/{image}")
        posts.append(
            {
                "title": meta["title"],
                "slug": slug,
                "date": date,
                "summary": meta["summary"],
                "image": image,
                "body_html": markdown.markdown(body, extensions=["sane_lists"]),
                "source": path.name,
            }
        )
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


def page_shell(
    *,
    title: str,
    description: str,
    current: str,
    content: str,
    year: int,
) -> str:
    def nav_link(href: str, label: str, key: str) -> str:
        current_attr = ' aria-current="page"' if current == key else ""
        return f'<a href="{href}"{current_attr}>{html.escape(label)}</a>'

    nav = "\n          ".join(
        [
            nav_link("/", "Home", "home"),
            nav_link("/tips/", "All Tips", "tips"),
            f'<a href="{JOIN_URL}">{html.escape(JOIN_NAV)}</a>',
        ]
    )
    page_title = title if title == SITE_NAME else f"{title} | {SITE_NAME}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta name="theme-color" content="#0a0a0a">
  <link rel="icon" href="/favicon.png" type="image/png" sizes="64x64">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="stylesheet" href="/css/styles.css">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="header-inner">
      <a class="wordmark" href="/">
        <img src="/images/logo-header.png" alt="One Minute Interview Tips" width="189" height="48">
      </a>
      <nav class="site-nav" aria-label="Primary">
          {nav}
      </nav>
    </div>
  </header>
  <main id="main">
    <div class="main-inner">
{content}
    </div>
  </main>
  <footer class="site-footer">
    <div class="footer-inner">
      <p>&copy; {year} {html.escape(SITE_NAME)}</p>
      <p><a href="{JOIN_URL}">{html.escape(JOIN_CTA)}</a></p>
    </div>
  </footer>
</body>
</html>
"""


def tip_list_html(posts: list[dict]) -> str:
    items = []
    for post in posts:
        items.append(
            f"""        <li>
          <a class="card" href="/tips/{html.escape(post['slug'])}/">
            <time datetime="{post['date'].isoformat()}">{html.escape(format_date(post['date']))}</time>
            <h2>{html.escape(post['title'])}</h2>
            <p class="summary">{html.escape(post['summary'])}</p>
          </a>
        </li>"""
        )
    return "      <ul class=\"tip-list\">\n" + "\n".join(items) + "\n      </ul>"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_static() -> None:
    if not STATIC_DIR.is_dir():
        return
    for src in STATIC_DIR.rglob("*"):
        if src.is_file():
            dest = DIST_DIR / src.relative_to(STATIC_DIR)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix == ".b64":
                # Binary assets are stored as base64 text; decode on build.
                dest.with_suffix("").write_bytes(base64.b64decode(src.read_text()))
            else:
                shutil.copy2(src, dest)


def build() -> int:
    posts = load_posts()
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)
    copy_static()
    year = dt.date.today().year

    home = f"""      <section class="intro">
        <h1>One-minute tips for interviews and the job search</h1>
        <p>Short, practical advice you can use today. New tips also go out in the Job Seekers community.</p>
        <p class="byline">From Gus Cawley, recruiter and CPA.</p>
      </section>
{tip_list_html(posts)}"""
    write(
        DIST_DIR / "index.html",
        page_shell(
            title=SITE_NAME,
            description="Short, practical one-minute interview and job-search tips from recruiter Gus Cawley.",
            current="home",
            content=home,
            year=year,
        ),
    )

    archive = f"""      <h1 class="page-title">All tips</h1>
{tip_list_html(posts)}"""
    write(
        DIST_DIR / "tips" / "index.html",
        page_shell(
            title="All tips",
            description="An archive of one-minute interview and job-search tips.",
            current="tips",
            content=archive,
            year=year,
        ),
    )

    for post in posts:
        image_html = ""
        if post["image"]:
            image_html = (
                f'        <img class="hero" src="/images/{html.escape(post["image"])}" '
                f'alt="{html.escape(post["title"])}">\n'
            )
        body = f"""      <article class="tip">
        <p class="kicker">Daily job tip</p>
        <h1>{html.escape(post['title'])}</h1>
        <p class="date"><time datetime="{post['date'].isoformat()}">{html.escape(format_date(post['date']))}</time></p>
{image_html}        <div class="prose">
          {post['body_html']}
        </div>
        <p class="cta"><a href="{JOIN_URL}">{html.escape(JOIN_CTA)}</a></p>
        <p><a class="back" href="/tips/">All tips</a></p>
      </article>"""
        write(
            DIST_DIR / "tips" / post["slug"] / "index.html",
            page_shell(
                title=post["title"],
                description=post["summary"],
                current="tip",
                content=body,
                year=year,
            ),
        )

    print(f"Built {len(posts)} tips into {DIST_DIR}")
    for post in posts:
        print(f"  /tips/{post['slug']}/  {post['title']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(build())
    except Exception as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)
