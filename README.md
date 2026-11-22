# One Minute Interview Tips

A small static site for [oneminuteinterviewtips.com](https://oneminuteinterviewtips.com). It is a home for short interview and job-search tips that also get posted in the [Job Seekers community](https://www.skool.com/jobseekers).

The site is plain HTML and CSS. A short Python script turns markdown files in `posts/` into pages in `dist/`.

## Add a tip

1. Create a new markdown file in `posts/`, for example `posts/my-new-tip.md`.
2. Start the file with front matter, then the tip body:

        ---
        title: The tip title
        slug: the-tip-title
        date: 2026-11-22
        summary: One line that appears in the tip list.
        image: optional-image.jpg
        ---

        Your tip, about 120 to 200 words.

3. If you include an `image`, put the file in `static/images/` and use only the file name in front matter. The image field is optional.
4. From the project root, run the build (see below). The new tip will show up on the home page, on `/tips/`, and at `/tips/your-slug/`.

Use a unique slug made of lowercase letters, numbers, and hyphens. Dates should be `YYYY-MM-DD`. Tips are listed newest first.

## Build

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build.py
```

The script rebuilds `dist/` each time. Do not edit files in `dist/` by hand.

## Preview

After a build:

```bash
python -m http.server --directory dist 8000
```

Then open [http://localhost:8000](http://localhost:8000). Tip pages live at `/tips/<slug>/`.

## Deploy

`render.yaml` describes a Render static site. The build command installs requirements and runs `python build.py`. The published folder is `dist`. Point the domain at that service when you are ready. This repo scaffold does not change DNS or create a Render service on its own.
