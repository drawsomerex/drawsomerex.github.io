#!/usr/bin/env python3
"""
Static Website Generator for Most Fascinating Stories Podcast.
Reads feed.xml and local chapter/transcript assets to generate
a self-contained, high-performance static index.html for GitHub Pages.
"""

import os
import re
import json
import html
import datetime
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHOW_DIR = os.path.join(REPO_ROOT, "src", "site", "podcasts", "most-fascinating-stories")
FEED_PATH = os.path.join(SHOW_DIR, "feed.xml")
OUTPUT_HTML = os.path.join(SHOW_DIR, "index.html")

def format_duration(seconds):
    try:
        s = int(seconds)
        m = s // 60
        sec = s % 60
        return f"{m} min {sec:02d} sec"
    except (ValueError, TypeError):
        return ""

def format_pub_date(rfc_str):
    try:
        # e.g., Thu, 22 Oct 2026 15:00:00 +0000
        dt = datetime.datetime.strptime(rfc_str[:25].strip(), "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%B %d, %Y")
    except Exception:
        return rfc_str

def parse_description_sections(raw_desc):
    parts = raw_desc.split("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    synopsis = ""
    chapters_text = ""
    sources_text = ""
    transcript_text = ""

    remaining = parts
    if len(parts) > 0:
        first_part = parts[0].strip()
        if "ko-fi.com" in first_part or "autonomousmedialab" in first_part:
            # Top links section! Next part is synopsis
            if len(parts) > 1:
                synopsis = parts[1].strip()
                remaining = parts[2:]
            else:
                remaining = []
        else:
            synopsis = first_part
            remaining = parts[1:]

    for section in remaining:
        s = section.strip()
        lines = s.split("\n")
        header = lines[0].strip().upper()
        content = "\n".join(lines[1:]).strip()

        if "CHAPTER" in header:
            chapters_text = content
        elif "SOURCE" in header or "REFERENCE" in header:
            sources_text = content
        elif "TRANSCRIPT" in header:
            transcript_text = content

    return synopsis, chapters_text, sources_text, transcript_text

def format_transcript_html(raw_transcript):
    if not raw_transcript:
        return ""
    
    html_lines = []
    # Match [Speaker - Role] or [Speaker]
    paragraphs = raw_transcript.split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Check for speaker tag
        match = re.match(r"^\[([A-Za-z0-9\s\-]+)\]\s*(.*)", para, re.DOTALL)
        if match:
            speaker = match.group(1).strip()
            text = html.escape(match.group(2).strip())
            is_host = "host" in speaker.lower() or "rebecca" in speaker.lower()
            badge_class = "speaker-host" if is_host else "speaker-guest"
            html_lines.append(f"""
            <div class="transcript-block">
              <span class="speaker-badge {badge_class}">{html.escape(speaker)}</span>
              <p class="transcript-text">{text}</p>
            </div>
            """)
        else:
            html_lines.append(f"""
            <div class="transcript-block">
              <p class="transcript-text">{html.escape(para)}</p>
            </div>
            """)

    return "\n".join(html_lines)

def format_sources_html(raw_sources):
    if not raw_sources:
        return ""
    
    html_lines = []
    for line in raw_sources.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("•") or line.startswith("-") or line.startswith("*"):
            item_text = line.lstrip("•-* ").strip()
            # Convert *Title* to <em>Title</em>
            formatted = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html.escape(item_text))
            html_lines.append(f"<li>{formatted}</li>")
        else:
            formatted = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html.escape(line))
            html_lines.append(f"<p>{formatted}</p>")

    if html_lines:
        return f'<ul class="sources-list">\n' + "\n".join(html_lines) + '\n</ul>'
    return ""

def load_chapters_json(chap_filename):
    if not chap_filename:
        return []
    local_path = os.path.join(SHOW_DIR, os.path.basename(chap_filename))
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("chapters", [])
        except Exception:
            pass
    return []

def generate_site():
    if not os.path.exists(FEED_PATH):
        print(f"Error: feed.xml not found at {FEED_PATH}")
        return False

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "podcast": "https://podcastindex.org/namespace/1.0"
    }

    tree = ET.parse(FEED_PATH)
    channel = tree.getroot().find("channel")
    if channel is None:
        print("Error: No channel found in feed.xml")
        return False

    show_title = channel.find("title").text if channel.find("title") is not None else "Most Fascinating Stories"
    show_desc = channel.find("description").text if channel.find("description") is not None else ""
    feed_url = "https://drawsomerex.github.io/podcasts/most-fascinating-stories/feed.xml"
    cover_url = "cover.jpg"

    guid_el = channel.find("podcast:guid", ns)
    podcast_guid = guid_el.text if guid_el is not None else "9c5d0f36-0b65-4a0e-cba4-5f4062ef3303"
    podcast_index_url = f"https://podcastindex.org/podcast/{podcast_guid}"

    items = channel.findall("item")
    episodes_data = []

    for idx, item in enumerate(items):
        title = item.find("title").text if item.find("title") is not None else f"Episode {idx+1}"
        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
        raw_desc = item.find("description").text if item.find("description") is not None else ""
        
        enclosure = item.find("enclosure")
        audio_url = enclosure.attrib.get("url", "") if enclosure is not None else ""
        audio_length = enclosure.attrib.get("length", "") if enclosure is not None else ""

        dur = item.find("itunes:duration", ns).text if item.find("itunes:duration", ns) is not None else ""
        ep_num = item.find("itunes:episode", ns).text if item.find("itunes:episode", ns) is not None else str(len(items) - idx)
        
        chap_el = item.find("podcast:chapters", ns)
        chap_url = chap_el.attrib.get("url", "") if chap_el is not None else ""
        
        trans_el = item.find("podcast:transcript", ns)
        trans_url = trans_el.attrib.get("url", "") if trans_el is not None else ""

        chapters_list = load_chapters_json(chap_url)
        synopsis, chapters_text, sources_text, transcript_text = parse_description_sections(raw_desc)

        episodes_data.append({
            "idx": idx,
            "ep_num": ep_num,
            "title": title,
            "pub_date": pub_date,
            "formatted_date": format_pub_date(pub_date),
            "duration": dur,
            "formatted_duration": format_duration(dur),
            "audio_url": audio_url,
            "audio_length": audio_length,
            "chap_url": chap_url,
            "trans_url": trans_url,
            "chapters_list": chapters_list,
            "synopsis": synopsis,
            "chapters_text": chapters_text,
            "sources_text": sources_text,
            "transcript_text": transcript_text
        })

    # Render episode cards
    episode_cards_html = []
    for i, ep in enumerate(episodes_data):
        # Guideline: First player above fold is eager, offscreen players below fold use loading="lazy"
        loading_attr = 'loading="lazy"' if i > 0 else ''
        card_id = f"ep-{ep['ep_num']}"
        player_id = f"player-{ep['ep_num']}"

        # Chapter pill buttons
        chap_buttons = []
        if ep["chapters_list"]:
            for ch in ep["chapters_list"]:
                sec = int(ch.get("startTime", 0))
                m = sec // 60
                s = sec % 60
                ts = f"{m:02d}:{s:02d}"
                ch_title = html.escape(ch.get("title", ""))
                chap_buttons.append(
                    f'<button type="button" class="chapter-btn" onclick="seekAudio(\'{player_id}\', {sec})" title="Jump to {ts}">'
                    f'<span class="ch-time">{ts}</span> <span class="ch-title">{ch_title}</span>'
                    f'</button>'
                )
        chap_bar_html = f'<div class="chapters-bar">{"".join(chap_buttons)}</div>' if chap_buttons else ''

        # Sources HTML
        sources_html = format_sources_html(ep["sources_text"])
        # Transcript HTML
        transcript_html = format_transcript_html(ep["transcript_text"])

        # VTT track tag
        track_tag = ""
        if ep["trans_url"]:
            vtt_local = os.path.basename(ep["trans_url"])
            track_tag = f'<track kind="captions" src="{vtt_local}" srclang="en" label="English" default>'

        # Details accordion group name
        details_name = f"accordion-ep-{ep['ep_num']}"

        card_html = f"""
        <article class="episode-card" id="{card_id}" data-title="{html.escape(ep['title'].lower())}" data-desc="{html.escape(ep['synopsis'].lower())}">
          <header class="episode-header">
            <div class="episode-meta-badges">
              <span class="badge ep-badge">Episode {ep['ep_num']}</span>
              <span class="badge date-badge">{ep['formatted_date']}</span>
              <span class="badge dur-badge">⏱ {ep['formatted_duration']}</span>
            </div>
            <h2 class="episode-title">{html.escape(ep['title'])}</h2>
          </header>

          <div class="player-wrapper">
            <figure class="media-figure">
              <figcaption class="sr-only">Audio player for {html.escape(ep['title'])}</figcaption>
              <audio id="{player_id}" controls {loading_attr} preload="metadata" src="{ep['audio_url']}" aria-label="Listen to {html.escape(ep['title'])}">
                {track_tag}
                Your browser does not support the audio element.
              </audio>
            </figure>
            {chap_bar_html}
          </div>

          <div class="episode-synopsis">
            <p>{html.escape(ep['synopsis'])}</p>
          </div>

          <div class="episode-disclosures">
            {f'''
            <details class="disclosure" name="{details_name}">
              <summary><span>📚 Historical Sources & References</span></summary>
              <div class="disclosure-content">
                {sources_html}
              </div>
            </details>
            ''' if sources_html else ''}

            {f'''
            <details class="disclosure" name="{details_name}">
              <summary><span>🎙️ Full Dialogue Transcript</span></summary>
              <div class="disclosure-content transcript-container">
                {transcript_html}
              </div>
            </details>
            ''' if transcript_html else ''}
          </div>

          <footer class="episode-footer">
            <a href="{ep['audio_url']}" download class="action-link" target="_blank" rel="noopener">
              ⬇ Download Audio ({int(int(ep['audio_length'] or 15000000) / 1024 / 1024)} MB)
            </a>
            {f'<a href="{os.path.basename(ep["trans_url"])}" download class="action-link" target="_blank" rel="noopener">📄 Download Transcript (.vtt)</a>' if ep['trans_url'] else ''}
            {f'<a href="{os.path.basename(ep["chap_url"])}" download class="action-link" target="_blank" rel="noopener">📑 Chapters (.json)</a>' if ep['chap_url'] else ''}
          </footer>
        </article>
        """
        episode_cards_html.append(card_html)

    # Full HTML Page Template
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(show_title)} — Autonomous History Podcast</title>
  <meta name="description" content="{html.escape(show_desc[:160])}">
  
  <!-- Open Graph / Social Sharing -->
  <meta property="og:type" content="website">
  <meta property="og:title" content="{html.escape(show_title)}">
  <meta property="og:description" content="{html.escape(show_desc[:200])}">
  <meta property="og:image" content="https://drawsomerex.github.io/podcasts/most-fascinating-stories/cover.jpg">
  <meta property="og:url" content="https://drawsomerex.github.io/podcasts/most-fascinating-stories/">
  <meta name="twitter:card" content="summary_large_image">
  
  <link rel="alternate" type="application/rss+xml" title="{html.escape(show_title)}" href="{feed_url}">
  <link rel="icon" type="image/jpeg" href="cover.jpg">

  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover: rgba(255, 255, 255, 0.12);
      --text: #e6edf3;
      --text-muted: #8b949e;
      --text-secondary: #c9d1d9;
      --accent: #f59e0b;
      --accent-hover: #d97706;
      --accent-soft: rgba(245, 158, 11, 0.12);
      --host-color: #38bdf8;
      --guest-color: #a78bfa;
      --radius: 12px;
      --radius-sm: 6px;
      --font-main: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }}

    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f8fafc;
        --card-bg: #ffffff;
        --card-border: #e2e8f0;
        --card-hover: #cbd5e1;
        --text: #0f172a;
        --text-muted: #64748b;
        --text-secondary: #334155;
        --accent: #d97706;
        --accent-hover: #b45309;
        --accent-soft: rgba(217, 119, 6, 0.1);
        --host-color: #0284c7;
        --guest-color: #7c3aed;
      }}
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-main);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      padding-bottom: 80px;
    }}

    a {{
      color: var(--accent);
      text-decoration: none;
      transition: color 0.15s ease;
    }}
    a:hover {{
      color: var(--accent-hover);
      text-decoration: underline;
    }}

    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border-width: 0;
    }}

    .container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 0 20px;
    }}

    /* HERO HEADER */
    .hero {{
      padding: 48px 0 32px 0;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 36px;
    }}

    .hero-grid {{
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 32px;
      align-items: center;
    }}

    @media (max-width: 700px) {{
      .hero-grid {{
        grid-template-columns: 1fr;
        text-align: center;
        gap: 24px;
      }}
      .hero-cover {{
        margin: 0 auto;
      }}
    }}

    .hero-cover {{
      width: 240px;
      height: 240px;
      border-radius: var(--radius);
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
      object-fit: cover;
      display: block;
    }}

    .hero-badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    @media (max-width: 700px) {{
      .hero-badge-row {{
        justify-content: center;
      }}
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid var(--accent-soft);
    }}

    .badge.ep-badge {{
      background: var(--accent);
      color: #000000;
      font-weight: 700;
    }}

    .badge.date-badge, .badge.dur-badge {{
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-muted);
      border-color: var(--card-border);
    }}

    .hero-title {{
      font-size: 2.25rem;
      font-weight: 800;
      line-height: 1.2;
      margin-bottom: 8px;
      letter-spacing: -0.02em;
    }}

    .hero-subtitle {{
      color: var(--text-muted);
      font-size: 0.95rem;
      margin-bottom: 14px;
      font-weight: 500;
    }}

    .hero-desc {{
      color: var(--text-secondary);
      font-size: 0.95rem;
      line-height: 1.55;
      margin-bottom: 24px;
    }}

    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    @media (max-width: 700px) {{
      .hero-actions {{
        justify-content: center;
      }}
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      border-radius: var(--radius-sm);
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
      text-decoration: none !important;
    }}

    .btn-primary {{
      background: var(--accent);
      color: #000000;
    }}
    .btn-primary:hover {{
      background: var(--accent-hover);
      color: #000000;
      transform: translateY(-1px);
    }}

    .btn-secondary {{
      background: var(--card-bg);
      color: var(--text);
      border-color: var(--card-border);
    }}
    .btn-secondary:hover {{
      border-color: var(--card-hover);
      background: rgba(255, 255, 255, 0.05);
      transform: translateY(-1px);
    }}

    /* CONTROLS BAR: SEARCH & FILTER */
    .controls-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      gap: 16px;
      flex-wrap: wrap;
    }}

    .search-box {{
      flex: 1;
      min-width: 240px;
      position: relative;
    }}

    .search-input {{
      width: 100%;
      padding: 10px 14px 10px 36px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--card-border);
      background: var(--card-bg);
      color: var(--text);
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.15s ease;
    }}
    .search-input:focus {{
      border-color: var(--accent);
    }}
    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 0.85rem;
      color: var(--text-muted);
      pointer-events: none;
    }}

    .count-indicator {{
      color: var(--text-muted);
      font-size: 0.85rem;
      font-weight: 500;
    }}

    /* EPISODE CARDS */
    .episodes-list {{
      display: flex;
      flex-direction: column;
      gap: 28px;
    }}

    .episode-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: var(--radius);
      padding: 24px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    .episode-card:hover {{
      border-color: var(--card-hover);
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
    }}

    .episode-meta-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }}

    .episode-title {{
      font-size: 1.35rem;
      font-weight: 700;
      line-height: 1.3;
      margin-bottom: 16px;
      color: var(--text);
    }}

    .player-wrapper {{
      margin-bottom: 16px;
      background: rgba(0, 0, 0, 0.2);
      padding: 12px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--card-border);
    }}

    audio {{
      width: 100%;
      height: 40px;
      border-radius: var(--radius-sm);
      outline: none;
    }}

    /* Chapter quick buttons */
    .chapters-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--card-border);
    }}

    .chapter-btn {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-secondary);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
    }}
    .chapter-btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
      background: var(--accent-soft);
    }}
    .chapter-btn .ch-time {{
      font-family: var(--font-mono);
      color: var(--accent);
      font-weight: 600;
    }}

    .episode-synopsis {{
      color: var(--text-secondary);
      font-size: 0.95rem;
      line-height: 1.6;
      margin-bottom: 18px;
    }}

    /* DISCLOSURES (ACCORDION) */
    .episode-disclosures {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 16px;
    }}

    details.disclosure {{
      border: 1px solid var(--card-border);
      border-radius: var(--radius-sm);
      background: rgba(255, 255, 255, 0.02);
      overflow: hidden;
    }}

    details.disclosure summary {{
      padding: 10px 14px;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      transition: color 0.15s ease, background 0.15s ease;
    }}
    details.disclosure summary:hover {{
      color: var(--text);
      background: rgba(255, 255, 255, 0.04);
    }}
    details.disclosure[open] summary {{
      color: var(--accent);
      border-bottom: 1px solid var(--card-border);
    }}

    .disclosure-content {{
      padding: 14px 16px;
      font-size: 0.9rem;
      color: var(--text-secondary);
      line-height: 1.6;
    }}

    .sources-list {{
      padding-left: 20px;
    }}
    .sources-list li {{
      margin-bottom: 6px;
    }}

    .transcript-container {{
      max-height: 380px;
      overflow-y: auto;
      padding-right: 8px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      scrollbar-width: thin;
      scrollbar-color: var(--card-border) transparent;
    }}

    .transcript-block {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}

    .speaker-badge {{
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .speaker-host {{
      color: var(--host-color);
    }}
    .speaker-guest {{
      color: var(--guest-color);
    }}

    .transcript-text {{
      font-size: 0.875rem;
      color: var(--text-secondary);
      line-height: 1.5;
    }}

    .episode-footer {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--card-border);
      font-size: 0.8rem;
    }}

    .action-link {{
      color: var(--text-muted);
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .action-link:hover {{
      color: var(--accent);
      text-decoration: none;
    }}

    /* SITE FOOTER */
    .site-footer {{
      margin-top: 60px;
      padding-top: 24px;
      border-top: 1px solid var(--card-border);
      text-align: center;
      color: var(--text-muted);
      font-size: 0.825rem;
      line-height: 1.6;
    }}

    .toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--accent);
      color: #000000;
      padding: 10px 18px;
      border-radius: var(--radius-sm);
      font-weight: 600;
      font-size: 0.875rem;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
      opacity: 0;
      transform: translateY(10px);
      transition: all 0.2s ease;
      pointer-events: none;
      z-index: 1000;
    }}
    .toast.show {{
      opacity: 1;
      transform: translateY(0);
    }}
  </style>
</head>
<body>

  <header class="hero">
    <div class="container">
      <div class="hero-grid">
        <img class="hero-cover" src="{cover_url}" alt="Most Fascinating Stories Podcast Cover Art" width="240" height="240" fetchpriority="high">
        <div class="hero-content">
          <div class="hero-badge-row">
            <span class="badge">History Documentary</span>
            <span class="badge">Tuesdays & Thursdays • 10 AM CT</span>
            <span class="badge">Podcast 2.0 Certified</span>
          </div>
          <h1 class="hero-title">{html.escape(show_title)}</h1>
          <p class="hero-subtitle">Hosted by Rebecca • Narrative Production by Autonomous Media Lab</p>
          <p class="hero-desc">{html.escape(show_desc)}</p>
          <div class="hero-actions">
            <a href="{feed_url}" class="btn btn-primary" target="_blank" rel="noopener">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="6.18" cy="17.82" r="2.18"/><path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.46-4.44-9.9-9.9-9.9z"/></svg>
              Subscribe via RSS
            </a>
            <button type="button" class="btn btn-secondary" onclick="copyFeedUrl()">
              📋 Copy RSS Link
            </button>
            <a href="{podcast_index_url}" class="btn btn-secondary" target="_blank" rel="noopener">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
              Podcast Index 2.0
            </a>
            <a href="https://ko-fi.com/autonomousmedialab" class="btn btn-secondary" target="_blank" rel="noopener">
              ☕ Tip Jar (Ko-fi)
            </a>
            <a href="https://autonomousmedialab.com/" class="btn btn-secondary" target="_blank" rel="noopener">
              🌐 Official Website
            </a>
          </div>
        </div>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="controls-bar">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input type="search" id="searchInput" class="search-input" placeholder="Search episodes by figure, topic, or keyword..." oninput="filterEpisodes()">
      </div>
      <div class="count-indicator" id="countIndicator">
        Showing {len(episodes_data)} of {len(episodes_data)} episodes
      </div>
    </div>

    <section class="episodes-list" id="episodesList">
      {"".join(episode_cards_html)}
    </section>

    <footer class="site-footer">
      <p><strong>Most Fascinating Stories</strong> is an autonomous history podcast published twice weekly on Tuesdays and Thursdays at 10:00 AM Central.</p>
      <p>Master audio hosted on Cloudflare R2 • Metadata & RSS statically distributed via GitHub Pages.</p>
      <p style="margin-top: 8px;">Content licensed under <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">Creative Commons Attribution 4.0 International (CC-BY-4.0)</a>.</p>
      <p style="margin-top: 4px;"><a href="https://ko-fi.com/autonomousmedialab" target="_blank" rel="noopener">☕ Tip Jar (Ko-fi)</a> • <a href="https://autonomousmedialab.com/" target="_blank" rel="noopener">🌐 Official Website</a> • <a href="{feed_url}">Raw RSS Feed XML</a> • <a href="{podcast_index_url}" target="_blank" rel="noopener">Podcast Index Listing</a> • <a href="https://github.com/drawsomerex/drawsomerex.github.io" target="_blank" rel="noopener">GitHub Repository</a></p>
    </footer>
  </main>

  <div id="toast" class="toast">Copied RSS Feed link to clipboard!</div>

  <script>
    // Audio Chapter Seek Helper
    function seekAudio(playerId, seconds) {{
      const audio = document.getElementById(playerId);
      if (audio) {{
        audio.currentTime = seconds;
        audio.play().catch(() => {{}});
      }}
    }}

    // Copy RSS URL to Clipboard
    function copyFeedUrl() {{
      const url = "{feed_url}";
      navigator.clipboard.writeText(url).then(() => {{
        const toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 2500);
      }}).catch(() => {{
        prompt("Copy RSS Feed URL:", url);
      }});
    }}

    // Client-side Instant Search Filter
    function filterEpisodes() {{
      const query = document.getElementById('searchInput').value.toLowerCase().trim();
      const cards = document.querySelectorAll('.episode-card');
      let visible = 0;

      cards.forEach(card => {{
        const title = card.getAttribute('data-title') || '';
        const desc = card.getAttribute('data-desc') || '';
        if (!query || title.includes(query) || desc.includes(query)) {{
          card.style.display = '';
          visible++;
        }} else {{
          card.style.display = 'none';
        }}
      }});

      const indicator = document.getElementById('countIndicator');
      indicator.textContent = `Showing ${{visible}} of ${{cards.length}} episodes`;
    }}

    // Dynamic Live Sync: Checks feed.xml on load to catch newly published episodes automatically
    async function syncLatestFromFeed() {{
      try {{
        const res = await fetch('feed.xml?t=' + Date.now());
        if (!res.ok) return;
        const text = await res.text();
        const parser = new DOMParser();
        const xml = parser.parseFromString(text, 'application/xml');
        const items = xml.querySelectorAll('channel > item');
        const currentCards = document.querySelectorAll('.episode-card');
        
        // If feed has more items than rendered cards, refresh page to show newly published episodes
        if (items.length > currentCards.length) {{
          console.log(`New episodes detected in feed (${{items.length}} vs ${{currentCards.length}}). Reloading view...`);
          window.location.reload();
        }}
      }} catch (err) {{
        // Non-blocking fallback
      }}
    }}
    syncLatestFromFeed();
  </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    print(f"Generated static website with {len(episodes_data)} episodes at:")
    print(f"  {OUTPUT_HTML}")
    return True

if __name__ == "__main__":
    generate_site()
