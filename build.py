#!/usr/bin/env python3
"""Build the One Minute Interview Tips static site from posts/*.md."""

from __future__ import annotations

import datetime as dt
import html
import re
import base64
import json
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
PAGES_DIR = ROOT / "pages"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

SITE_NAME = "One Minute Interview Tips"
SITE_URL = "https://www.oneminuteinterviewtips.com"
DEFAULT_IMAGE = "og-default.png"
JOIN_URL = "https://www.skool.com/jobseekers"
JOIN_NAV = "Join the community"
JOIN_CTA = "Join the Job Seekers community"
# Guide sections: folder under pages/ -> (URL prefix, hub title, hub description, kicker).
SECTIONS = {
    "questions": ("/questions/", "Common interview questions",
                  "How to answer the most common interview questions, with example answers and FAQs.",
                  "Interview question"),
    "roles": ("/roles/", "Interview tips by role",
              "Interview tips for accountants, paralegals, nurses, school therapists, sales, HR, and administrative roles.",
              "Interview tips by role"),
    "local": ("/", None, None, "Local interview tips"),
}
FAQ_HEADING = "## Frequently asked questions"
ORG = {
    "@type": "Organization",
    "@id": f"{SITE_URL}/#org",
    "name": SITE_NAME,
    "url": f"{SITE_URL}/",
    "logo": f"{SITE_URL}/apple-touch-icon.png",
    "sameAs": [JOIN_URL],
}
AUTHOR = {"@type": "Person", "@id": f"{SITE_URL}/#gus", "name": "Gus Cawley", "jobTitle": "Recruiter and CPA"}

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


def split_faq(body: str, name: str) -> tuple[str, list[tuple[str, str]]]:
    """Split the FAQ section off a guide. Questions are '### ' lines, answers plain text."""
    if FAQ_HEADING not in body:
        raise SystemExit(f"{name} is missing '{FAQ_HEADING}'")
    main, faq_text = body.split(FAQ_HEADING, 1)
    faqs = []
    for block in faq_text.split("### ")[1:]:
        q, _, a = block.strip().partition("\n")
        a = " ".join(a.split())
        if not q.strip() or not a:
            raise SystemExit(f"{name} has an empty FAQ entry")
        faqs.append((q.strip(), a))
    return main.strip(), faqs


def split_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def load_guides() -> list[dict]:
    guides = []
    for section, (prefix, *_rest, kicker) in SECTIONS.items():
        for path in sorted((PAGES_DIR / section).glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            for field in ("title", "slug", "date", "summary", "related"):
                if not meta.get(field):
                    raise SystemExit(f"{path.name} is missing '{field}'")
            if not SLUG_RE.match(meta["slug"]):
                raise SystemExit(f"{path.name} has an invalid slug")
            main, faqs = split_faq(body, path.name)
            guides.append(
                {
                    "title": meta["title"],
                    "slug": meta["slug"],
                    "section": section,
                    "kicker": kicker,
                    "path": f"{prefix}{meta['slug']}/",
                    "date": parse_date(meta["date"]),
                    "summary": meta["summary"],
                    "related": split_list(meta["related"]),
                    "tips": split_list(meta.get("tips", "")),
                    "body_html": markdown.markdown(main, extensions=["sane_lists"]),
                    "faqs": faqs,
                }
            )
    return guides


def page_shell(
    *,
    title: str,
    description: str,
    current: str,
    content: str,
    year: int,
    path: str,
    image: str | None = None,
    og_type: str = "website",
    jsonld: dict | None = None,
) -> str:
    def nav_link(href: str, label: str, key: str) -> str:
        current_attr = ' aria-current="page"' if current == key else ""
        return f'<a href="{href}"{current_attr}>{html.escape(label)}</a>'

    nav = "\n          ".join(
        [
            nav_link("/", "Home", "home"),
            nav_link("/tips/", "All Tips", "tips"),
            nav_link("/questions/", "Questions", "questions"),
            nav_link("/roles/", "By Role", "roles"),
            f'<a href="{JOIN_URL}">{html.escape(JOIN_NAV)}</a>',
        ]
    )
    page_title = title if title == SITE_NAME else f"{title} | {SITE_NAME}"
    url = SITE_URL + path
    image_url = f"{SITE_URL}/images/{image or DEFAULT_IMAGE}"
    t, d = html.escape(page_title), html.escape(description)
    social = f"""  <link rel="canonical" href="{url}">
  <meta property="og:site_name" content="{html.escape(SITE_NAME)}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{image_url}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{t}">
  <meta name="twitter:description" content="{d}">
  <meta name="twitter:image" content="{image_url}">"""
    if jsonld:
        data = json.dumps(jsonld, indent=2).replace("</", "<\\/")
        social += f'\n  <script type="application/ld+json">\n{data}\n  </script>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(description)}">
{social}
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


def breadcrumbs(items: list[tuple[str, str]]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + path}
            for i, (name, path) in enumerate(items, 1)
        ],
    }


def related_html(post: dict, posts: list[dict], count: int = 3) -> str:
    others = [p for p in posts if p["slug"] != post["slug"]][:count]
    if not others:
        return ""
    links = "\n".join(
        f'            <li><a href="/tips/{html.escape(p["slug"])}/">{html.escape(p["title"])}</a></li>'
        for p in others
    )
    return f"""        <section class="related" aria-labelledby="related-heading">
          <h2 id="related-heading">More one-minute tips</h2>
          <ul>
{links}
          </ul>
        </section>"""


def link_list_html(heading: str, hid: str, items: list[tuple[str, str]]) -> str:
    if not items:
        return ""
    links = "\n".join(
        f'            <li><a href="{html.escape(href)}">{html.escape(label)}</a></li>' for href, label in items
    )
    return f"""        <section class="related" aria-labelledby="{hid}">
          <h2 id="{hid}">{html.escape(heading)}</h2>
          <ul>
{links}
          </ul>
        </section>"""


def guide_cards_html(guides: list[dict], tag: str = "h2") -> str:
    items = "\n".join(
        f"""        <li>
          <a class="card" href="{g['path']}">
            <{tag}>{html.escape(g['title'])}</{tag}>
            <p class="summary">{html.escape(g['summary'])}</p>
          </a>
        </li>"""
        for g in guides
    )
    return f'      <ul class="tip-list">\n{items}\n      </ul>'


def faq_html(faqs: list[tuple[str, str]]) -> str:
    items = "\n".join(
        f"          <h3>{html.escape(q)}</h3>\n          <p>{html.escape(a)}</p>" for q, a in faqs
    )
    return f"""        <section class="faq" aria-labelledby="faq-heading">
          <h2 id="faq-heading">Frequently asked questions</h2>
{items}
        </section>"""


def llms_txt(posts: list[dict], guides: list[dict]) -> str:
    lines = [
        f"# {SITE_NAME}",
        "",
        "> Short, practical interview and job-search tips you can read in about a minute, written by "
        "Gus Cawley, a recruiter and CPA in Atlanta, GA. New tips are posted here and shared in the "
        f"Job Seekers community on Skool ({JOIN_URL}).",
        "",
        "## Tips",
    ]
    lines += [f"- [{p['title']}]({SITE_URL}/tips/{p['slug']}/): {p['summary']}" for p in posts]
    for section, (prefix, hub_title, _desc, _kicker) in SECTIONS.items():
        lines += ["", f"## {hub_title or 'Local guides'}"]
        lines += [f"- [{g['title']}]({SITE_URL}{g['path']}): {g['summary']}" for g in guides if g["section"] == section]
    lines += [
        "",
        "## Pages",
        f"- [Home]({SITE_URL}/): latest tips",
        f"- [All tips]({SITE_URL}/tips/): every tip, newest first",
        f"- [Common interview questions]({SITE_URL}/questions/): how to answer common questions",
        f"- [Interview tips by role]({SITE_URL}/roles/): tips for specific jobs and for Atlanta",
        f"- [Job Seekers community]({JOIN_URL}): community for job seekers",
        "",
    ]
    return "\n".join(lines)


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
    guides = load_guides()
    tip_titles = {p["slug"]: p["title"] for p in posts}
    guide_by_path = {g["path"]: g for g in guides}
    for g in guides:
        for ref in g["related"]:
            if ref not in guide_by_path:
                raise SystemExit(f"{g['slug']}: related page not found: {ref}")
        for ref in g["tips"]:
            if ref not in tip_titles:
                raise SystemExit(f"{g['slug']}: tip not found: {ref}")
    by_section = {s: [g for g in guides if g["section"] == s] for s in SECTIONS}
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
{tip_list_html(posts)}
{link_list_html("Common interview questions", "home-questions",
                [(g["path"], g["title"]) for g in by_section["questions"]] + [("/questions/", "See all question guides")])}
{link_list_html("Interview tips by role and city", "home-roles",
                [(g["path"], g["title"]) for g in by_section["roles"] + by_section["local"]] + [("/roles/", "See all role guides")])}"""
    write(
        DIST_DIR / "index.html",
        page_shell(
            title=SITE_NAME,
            description="Short, practical one-minute interview and job-search tips from recruiter Gus Cawley.",
            current="home",
            content=home,
            year=year,
            path="/",
            jsonld={
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "WebSite", "@id": f"{SITE_URL}/#site", "name": SITE_NAME,
                     "url": f"{SITE_URL}/", "publisher": {"@id": f"{SITE_URL}/#org"}},
                    ORG,
                    AUTHOR,
                ],
            },
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
            path="/tips/",
            jsonld={
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "CollectionPage", "name": "All tips", "url": f"{SITE_URL}/tips/",
                     "isPartOf": {"@id": f"{SITE_URL}/#site"}},
                    breadcrumbs([("Home", "/"), ("All tips", "/tips/")]),
                ],
            },
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
{related_html(post, posts)}
{link_list_html("Go deeper", "deeper-heading", [(g["path"], g["title"]) for g in guides if post["slug"] in g["tips"]])}
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
                path=f"/tips/{post['slug']}/",
                image=post["image"],
                og_type="article",
                jsonld={
                    "@context": "https://schema.org",
                    "@graph": [
                        {
                            "@type": "Article",
                            "headline": post["title"],
                            "description": post["summary"],
                            "datePublished": post["date"].isoformat(),
                            "image": f"{SITE_URL}/images/{post['image'] or DEFAULT_IMAGE}",
                            "author": AUTHOR,
                            "publisher": ORG,
                            "mainEntityOfPage": f"{SITE_URL}/tips/{post['slug']}/",
                        },
                        breadcrumbs([("Home", "/"), ("All tips", "/tips/"), (post["title"], f"/tips/{post['slug']}/")]),
                    ],
                },
            ),
        )

    for section, (prefix, hub_title, hub_desc, _kicker) in SECTIONS.items():
        if not hub_title:
            continue
        hub_body = f"""      <section class="intro">
        <h1>{html.escape(hub_title)}</h1>
        <p>{html.escape(hub_desc)}</p>
        <p class="byline">From Gus Cawley, recruiter and CPA.</p>
      </section>
{guide_cards_html(by_section[section])}"""
        if section == "roles":
            hub_body += "\n      <h2 class=\"section-title\">By city</h2>\n" + guide_cards_html(by_section["local"], "h3")
            hub_body += '\n      <p class="note">Looking for open jobs? Browse <a href="https://www.100xjobs.com/">100X Jobs</a>.</p>'
        members = by_section[section] + (by_section["local"] if section == "roles" else [])
        write(
            DIST_DIR / prefix.strip("/") / "index.html",
            page_shell(
                title=hub_title,
                description=hub_desc,
                current=section,
                content=hub_body,
                year=year,
                path=prefix,
                jsonld={
                    "@context": "https://schema.org",
                    "@graph": [
                        {"@type": "CollectionPage", "name": hub_title, "url": SITE_URL + prefix,
                         "description": hub_desc, "isPartOf": {"@id": f"{SITE_URL}/#site"},
                         "hasPart": [{"@type": "Article", "headline": g["title"], "url": SITE_URL + g["path"]}
                                     for g in members]},
                        breadcrumbs([("Home", "/"), (hub_title, prefix)]),
                    ],
                },
            ),
        )

    for g in guides:
        prefix, hub_title = SECTIONS[g["section"]][:2]
        hub_path = prefix if hub_title else "/roles/"
        hub_name = hub_title or SECTIONS["roles"][1]
        crumbs = [("Home", "/")] + ([(hub_title, prefix)] if hub_title else []) + [(g["title"], g["path"])]
        related = [(r, guide_by_path[r]["title"]) for r in g["related"]]
        tips = [(f"/tips/{t}/", tip_titles[t]) for t in g["tips"]]
        body = f"""      <article class="tip">
        <p class="kicker"><a href="{hub_path}">{html.escape(g['kicker'])}</a></p>
        <h1>{html.escape(g['title'])}</h1>
        <p class="date">By Gus Cawley, recruiter and CPA &middot; <time datetime="{g['date'].isoformat()}">{html.escape(format_date(g['date']))}</time></p>
        <div class="prose">
          {g['body_html']}
        </div>
{faq_html(g['faqs'])}
        <p class="cta"><a href="{JOIN_URL}">{html.escape(JOIN_CTA)}</a></p>
{link_list_html("Related guides", "related-heading", related)}
{link_list_html("Quick tips on this topic", "tips-heading", tips)}
        <p><a class="back" href="{hub_path}">All {html.escape(hub_name.lower())}</a></p>
      </article>"""
        write(
            DIST_DIR / g["path"].strip("/") / "index.html",
            page_shell(
                title=g["title"],
                description=g["summary"],
                current=g["section"] if hub_title else "roles",
                content=body,
                year=year,
                path=g["path"],
                og_type="article",
                jsonld={
                    "@context": "https://schema.org",
                    "@graph": [
                        {
                            "@type": "Article",
                            "headline": g["title"],
                            "description": g["summary"],
                            "datePublished": g["date"].isoformat(),
                            "image": f"{SITE_URL}/images/{DEFAULT_IMAGE}",
                            "author": AUTHOR,
                            "publisher": ORG,
                            "mainEntityOfPage": SITE_URL + g["path"],
                        },
                        breadcrumbs(crumbs),
                        {
                            "@type": "FAQPage",
                            "mainEntity": [
                                {"@type": "Question", "name": q,
                                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                                for q, a in g["faqs"]
                            ],
                        },
                    ],
                },
            ),
        )

    write(DIST_DIR / "llms.txt", llms_txt(posts, guides))
    write(DIST_DIR / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    latest = max(p["date"] for p in posts + guides).isoformat()
    entries = [("/", latest), ("/tips/", latest)] + [
        (f"/tips/{p['slug']}/", p["date"].isoformat()) for p in posts
    ]
    for section, (prefix, hub_title, *_rest) in SECTIONS.items():
        members = by_section[section]
        if hub_title:
            entries.append((prefix, max(g["date"] for g in members).isoformat()))
        entries += [(g["path"], g["date"].isoformat()) for g in members]
    urls = "\n".join(
        f"  <url><loc>{SITE_URL}{loc}</loc><lastmod>{mod}</lastmod></url>" for loc, mod in entries
    )
    write(
        DIST_DIR / "sitemap.xml",
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n",
    )

    print(f"Built {len(posts)} tips and {len(guides)} guides into {DIST_DIR}")
    for g in guides:
        print(f"  {g['path']}  {g['title']}")
    for post in posts:
        print(f"  /tips/{post['slug']}/  {post['title']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(build())
    except Exception as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)
