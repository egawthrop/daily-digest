# The Daily Digest

A tiny, self-updating news digest. Every morning a GitHub Action reads your list
of RSS feeds, grabs the **top story from each publication**, and writes it out as:

- `index.html` — a clean web page (serve it free with GitHub Pages)
- `feed.xml` — an RSS feed of the day's picks (subscribe from any reader, or a Kobo)
- `latest.md` — the same digest in Markdown
- `archive/YYYY-MM-DD.md` — a dated copy so you build up a history

No server to run, nothing to keep awake, no scraping — it reads the feeds each
publication already publishes, so it stays robust when sites redesign.

## Setup (about 5 minutes)

1. **Create a repo** and add these files to it (keep the folder structure):
   ```
   digest.py
   feeds.txt
   requirements.txt
   .github/workflows/digest.yml
   ```

2. **Pick your sources.** Edit `feeds.txt`. One line per publication:
   ```
   Name | https://feed-url
   ```
   Most outlets publish an RSS feed — search "`<publication> RSS`" to find it.
   A few starters are included; add or delete freely. The digest follows this order.

3. **Set your 6 AM time.** Open `.github/workflows/digest.yml` and edit the `cron`
   line. GitHub schedules in **UTC**, so use the UTC time that equals 6 AM for you.
   The file lists the common conversions. (Default is 11:00 UTC = 6 AM US Eastern.)
   Also set `DIGEST_TZ` in that file to your timezone (e.g. `Europe/London`) so the
   on-page date and time read correctly.

4. **Allow the Action to commit.** In your repo: **Settings → Actions → General →
   Workflow permissions → Read and write permissions → Save.**

5. **Test it now.** Go to the **Actions** tab → *Daily Digest* → **Run workflow**.
   After it finishes, `index.html` and `latest.md` will appear in your repo, updated.

## Read it as a web page (optional)

Turn on **Settings → Pages → Build from branch → `main` / root**. Your digest will
be live at `https://<your-username>.github.io/<repo>/`. Bookmark it on your phone,
or use your browser's **"Add to Home Screen"** to get a full-screen, app-like icon.

The main page shows today's stories with a **"Past digests"** list at the bottom
that links to every archived day; each archive page has a "Back to latest" link at
the top. So you can browse history entirely by tapping, no URLs to type.

## Read it as an RSS feed (and on a Kobo)

Every run also writes `feed.xml` — a standard RSS feed with one item per source.
Once Pages is on, it's live at `https://<username>.github.io/<repo>/feed.xml`.
Set `SITE_URL` in the workflow (the "Build digest" step) to your Pages URL so the
feed references itself correctly.

Subscribe to that URL from any RSS reader. For a **Kobo**, note that Kobo's old
built-in Pocket sync was retired when Pocket shut down in 2025, so the simplest
free route now is **Calibre**:

1. Install Calibre (free): https://calibre-ebook.com
2. Open the included `daily_digest.recipe` and set `FEED_URL` to your `feed.xml`.
3. Calibre → **Fetch news → Add a custom news source → load recipe from file**,
   pick that file, then **Fetch news**. Calibre builds a clean EPUB.
4. Connect your Kobo (USB or Calibre's wireless device link) and send the EPUB.
5. Use Calibre's **Schedule** on that source to fetch it automatically each
   morning (Calibre must be running at that time).

The recipe fetches and cleans the full article text, so it reads well on e-ink.
If you'd rather have a hosted sync instead of running Calibre, any RSS-capable
read-later service that supports Kobo will accept the same `feed.xml` URL.

## Run it locally (optional)

```bash
pip install -r requirements.txt
python digest.py
```
Then open `index.html`.

## Notes

- If a feed is temporarily down or malformed, that one source shows a small
  "couldn't load" note and the rest of the digest still builds.
- "Top story" = the first item in each feed, which is how outlets order their
  feeds. If you'd rather rank by something else, that logic lives in
  `fetch_top_story()` in `digest.py`.
- GitHub doesn't observe daylight saving, so the local hour drifts by one when
  your region changes clocks; nudge the `cron` line twice a year if that bugs you.
