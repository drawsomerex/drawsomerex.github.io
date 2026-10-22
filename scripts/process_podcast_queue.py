#!/usr/bin/env python3
"""
Autonomous Multi-Show Podcast Queue Processor for GitHub Pages.
Scans src/site/podcasts/_queue/*/ for queued episodes whose scheduled_date <= current UTC.
When an episode is due:
1. Moves audio, vtt, and chapters into src/site/podcasts/<show_slug>/
2. Injects the <item> into src/site/podcasts/<show_slug>/feed.xml
3. Updates <lastBuildDate>
4. Removes the _meta.json file
Sets GitHub Actions env variable EPISODES_PUBLISHED=true if anything was released.
"""

import os
import sys
import json
import uuid
import shutil
import datetime
import email.utils
import xml.etree.ElementTree as ET
from xml.dom import minidom

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PODCASTS_DIR = os.path.join(REPO_ROOT, "src", "site", "podcasts")
QUEUE_DIR = os.path.join(PODCASTS_DIR, "_queue")

def format_rfc2822(dt):
    return email.utils.format_datetime(dt)

def process_queue():
    if not os.path.exists(QUEUE_DIR):
        print(f"No queue directory found at {QUEUE_DIR}")
        return False

    shows = [d for d in os.listdir(QUEUE_DIR) if os.path.isdir(os.path.join(QUEUE_DIR, d)) and not d.startswith(".")]
    if not shows:
        print("No shows currently in queue.")
        return False

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    published_any = False
    published_count = 0

    # Namespaces for RSS XML
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("podcast", "https://podcastindex.org/namespace/1.0")

    for show_slug in sorted(shows):
        show_queue_dir = os.path.join(QUEUE_DIR, show_slug)
        live_show_dir = os.path.join(PODCASTS_DIR, show_slug)
        feed_path = os.path.join(live_show_dir, "feed.xml")

        if not os.path.exists(feed_path):
            print(f"Warning: No feed.xml found for show '{show_slug}' at {feed_path}. Skipping.")
            continue

        meta_files = sorted([f for f in os.listdir(show_queue_dir) if f.endswith("_meta.json")])
        if not meta_files:
            continue

        print(f"\n--- Checking queue for show: {show_slug} ({len(meta_files)} queued) ---")

        # Parse existing feed.xml
        tree = ET.parse(feed_path)
        root = tree.getroot()
        channel = root.find("channel")
        if channel is None:
            print(f"Error: No channel found in {feed_path}")
            continue

        show_published_this_round = False

        for mf in meta_files:
            mf_path = os.path.join(show_queue_dir, mf)
            with open(mf_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            sch_str = meta.get("scheduled_date")
            if not sch_str:
                continue

            sch_dt = datetime.datetime.fromisoformat(sch_str.replace("Z", "+00:00"))
            if now_utc < sch_dt:
                print(f"Episode {meta.get('episode')}: '{meta.get('title')}' remains queued until {sch_str}")
                continue

            # TIME TO PUBLISH!
            print(f"\n🚀 Releasing Episode {meta.get('episode')}: '{meta.get('title')}' (scheduled: {sch_str})")
            
            # 1. Move media files
            audio_name = meta["audio"]
            src_audio = os.path.join(show_queue_dir, audio_name)
            dst_audio = os.path.join(live_show_dir, audio_name)
            if os.path.exists(src_audio):
                shutil.move(src_audio, dst_audio)
                print(f"  Moved audio: {audio_name}")

            base_slug = os.path.splitext(audio_name)[0]

            if meta.get("transcript"):
                vtt_name = meta["transcript"]
                src_vtt = os.path.join(show_queue_dir, vtt_name)
                dst_vtt = os.path.join(live_show_dir, vtt_name)
                if os.path.exists(src_vtt):
                    shutil.move(src_vtt, dst_vtt)
                    print(f"  Moved transcript: {vtt_name}")

            if meta.get("chapters"):
                chap_name = meta["chapters"]
                src_chap = os.path.join(show_queue_dir, chap_name)
                dst_chap = os.path.join(live_show_dir, chap_name)
                if os.path.exists(src_chap):
                    shutil.move(src_chap, dst_chap)
                    print(f"  Moved chapters: {chap_name}")

            # Also move any matching chapters.json or txt if present
            for ext in [".vtt", "_chapters.json", "_chapters.txt"]:
                extra_file = f"{base_slug}{ext}"
                extra_src = os.path.join(show_queue_dir, extra_file)
                extra_dst = os.path.join(live_show_dir, extra_file)
                if os.path.exists(extra_src):
                    shutil.move(extra_src, extra_dst)

            # 2. Construct XML item
            item = ET.Element("item")
            ET.SubElement(item, "title").text = meta["title"]
            ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = meta.get("guid", str(uuid.uuid4()))
            ET.SubElement(item, "pubDate").text = format_rfc2822(sch_dt)
            ET.SubElement(item, "description").text = meta.get("description", "")

            # Audio enclosure
            base_url = f"https://drawsomerex.github.io/podcasts/{show_slug}"
            audio_size = os.path.getsize(dst_audio) if os.path.exists(dst_audio) else meta.get("size_bytes", 20000000)
            
            if meta.get("audio_url"):
                audio_enclosure_url = meta["audio_url"]
            elif show_slug == "most-fascinating-stories":
                audio_enclosure_url = f"https://pub-f97b46c0739c43598234830bfe564775.r2.dev/most-fascinating-stories/{audio_name}"
            elif show_slug == "line-by-line":
                audio_enclosure_url = f"https://archive.org/download/line-by-line-podcast/{audio_name}"
            else:
                audio_enclosure_url = f"{base_url}/{audio_name}"

            ET.SubElement(item, "enclosure", {
                "url": audio_enclosure_url,
                "length": str(audio_size),
                "type": "audio/mpeg"
            })

            dur_sec = meta.get("duration", int(audio_size / (192000 / 8)))
            ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration").text = str(dur_sec)
            ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}episode").text = str(meta.get("episode", 1))
            ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}season").text = str(meta.get("season", 1))
            ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = meta.get("explicit", "no")

            ET.SubElement(item, "{https://podcastindex.org/namespace/1.0}txt", {"purpose": "ai"}).text = (
                "Notice: This broadcast, voice narration, and script are generated autonomously by artificial intelligence."
            )

            chap_json_file = f"{base_slug}_chapters.json"
            if os.path.exists(os.path.join(live_show_dir, chap_json_file)):
                ET.SubElement(item, "{https://podcastindex.org/namespace/1.0}chapters", {
                    "url": f"{base_url}/{chap_json_file}",
                    "type": "application/json+chapters"
                })

            vtt_file = f"{base_slug}.vtt"
            if os.path.exists(os.path.join(live_show_dir, vtt_file)):
                ET.SubElement(item, "{https://podcastindex.org/namespace/1.0}transcript", {
                    "url": f"{base_url}/{vtt_file}",
                    "type": "text/vtt",
                    "language": meta.get("language", "en-us")
                })

            # Insert item at the top of the items list in channel
            first_item_idx = None
            for idx, child in enumerate(list(channel)):
                if child.tag == "item":
                    first_item_idx = idx
                    break

            if first_item_idx is not None:
                channel.insert(first_item_idx, item)
            else:
                channel.append(item)

            # Update lastBuildDate
            last_build = channel.find("lastBuildDate")
            if last_build is not None:
                last_build.text = format_rfc2822(now_utc)

            # Remove meta file
            os.remove(mf_path)
            published_any = True
            show_published_this_round = True
            published_count += 1

        if show_published_this_round:
            # Write back cleaned pretty XML
            xml_str = ET.tostring(root, encoding="utf-8")
            dom = minidom.parseString(xml_str)
            pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
            cleaned_lines = [l for l in pretty_xml.splitlines() if l.strip()]
            with open(feed_path, "w", encoding="utf-8") as f:
                f.write("\n".join(cleaned_lines) + "\n")
            print(f"Updated {feed_path} successfully!")

            # Regenerate static website
            if show_slug == "most-fascinating-stories":
                try:
                    sys.path.insert(0, os.path.dirname(__file__))
                    from generate_podcast_site import generate_site
                    generate_site()
                except Exception as e:
                    print(f"Notice: Could not regenerate static website: {e}")

    print(f"\nDone. Published {published_count} episode(s).")
    return published_any

if __name__ == "__main__":
    did_publish = process_queue()
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"EPISODES_PUBLISHED={'true' if did_publish else 'false'}\n")
    sys.exit(0)
