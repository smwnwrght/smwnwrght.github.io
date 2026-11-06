#!/usr/bin/env python3
"""
Sync Notion database to Hugo markdown files
Converts Notion blocks to Hugo-compatible markdown
"""

import hashlib
import json
import mimetypes
import os
import re
import requests
import shutil
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
# Configuration from environment variables
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DATABASE_ID = os.environ.get('NOTION_DATABASE_ID')
OUTPUT_DIR = 'content/posts'
# Notion API setup
NOTION_API = 'https://api.notion.com/v1'
HEADERS = {
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}
def check(response):
    """raise_for_status, but show Notion's explanation first"""
    if not response.ok:
        print(f'Notion API {response.status_code}: {response.text}')
    response.raise_for_status()
    return response


def query_database():
    """Fetch every (non-archived) page in the database, whatever its status"""
    # Read the schema so the filter matches the real property types
    schema = check(requests.get(f'{NOTION_API}/databases/{DATABASE_ID}', headers=HEADERS)).json()
    props = schema['properties']
    print('Database properties: ' + ', '.join(f"{k} ({v['type']})" for k, v in props.items()))

    status = props.get('Status')
    if not status or status['type'] not in ('status', 'select'):
        raise RuntimeError("No usable 'Status' property (need type 'status' or 'select')")

    data = {}
    sort_prop = next((n for n in ('Published Date', 'Date') if props.get(n, {}).get('type') == 'date'), None)
    if sort_prop:
        data['sorts'] = [{'property': sort_prop, 'direction': 'descending'}]

    results = []
    url = f'{NOTION_API}/databases/{DATABASE_ID}/query'
    while True:
        body = check(requests.post(url, headers=HEADERS, json=data)).json()
        results.extend(body['results'])
        if not body.get('has_more'):
            return [p for p in results if not p.get('archived') and not p.get('in_trash')]
        data['start_cursor'] = body['next_cursor']


def get_page_content(page_id):
    """Fetch all blocks from a Notion page (Notion returns at most 100 per request)"""
    url = f'{NOTION_API}/blocks/{page_id}/children'
    params = {'page_size': 100}
    blocks = []
    while True:
        body = check(requests.get(url, headers=HEADERS, params=params)).json()
        blocks.extend(body['results'])
        if not body.get('has_more'):
            return blocks
        params['start_cursor'] = body['next_cursor']


def page_status(page):
    """Name of the page's Status (works for both 'status' and 'select' properties)"""
    prop = page['properties'].get('Status') or {}
    value = prop.get(prop.get('type')) or {}
    return value.get('name')


def read_front_matter(path):
    """The simple `key: value` lines of a post's front matter, as a dict"""
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return {}
    parts = text.split('---', 2)
    if not text.startswith('---') or len(parts) < 3:
        return {}
    fields = {}
    for line in parts[1].splitlines():
        key, sep, value = line.partition(':')
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    return fields


def find_managed_posts():
    """Posts this script created, found by the notion_id in their front matter.

    Hand-written posts have no notion_id, so they are never touched.
    """
    managed = {}
    for path in Path(OUTPUT_DIR).glob('*/index.md'):
        notion_id = read_front_matter(path).get('notion_id')
        if notion_id:
            managed[notion_id] = path
    return managed


def mark_draft(path):
    """Set draft: true in a post's front matter, keeping everything else. True if it changed."""
    text = path.read_text(encoding='utf-8')
    parts = text.split('---', 2)
    new_front = re.sub(r'^draft:.*$', 'draft: true', parts[1], flags=re.M)
    if new_front == parts[1]:
        return False
    parts[1] = new_front
    path.write_text('---'.join(parts), encoding='utf-8')
    return True


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.avif'}


def download_image(url, block_id, post_dir):
    """Download an image into the post's folder and return its filename.

    Notion-hosted image URLs expire after about an hour, so the file has to be
    copied into the repo. The name is a hash of the Notion block id so it stays
    the same between syncs. No Notion auth header is sent (the URLs are
    pre-signed S3 links and reject extra credentials).
    """
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        content_type = response.headers.get('Content-Type', '').split(';')[0].strip()
        ext = mimetypes.guess_extension(content_type) or '.png'
        ext = {'.jpe': '.jpg'}.get(ext, ext)
    # Hash the whole id: blocks created together share a long id prefix
    digest = hashlib.sha1(block_id.encode()).hexdigest()[:12]
    filename = f"image-{digest}{ext}"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / filename).write_bytes(response.content)
    return filename


def notion_to_markdown(blocks, post_dir=None, images=None):
    """Convert Notion blocks to markdown.

    Images are downloaded into post_dir (if given); their filenames are added
    to the `images` set so stale ones can be cleaned up afterwards.
    """
    markdown = []
    for block in blocks:
        block_type = block['type']
        # Paragraph
        if block_type == 'paragraph':
            text = rich_text_to_markdown(block['paragraph']['rich_text'])
            if text.strip():
                markdown.append(f'{text}\n')
        # Headings
        elif block_type == 'heading_1':
            text = rich_text_to_markdown(block['heading_1']['rich_text'])
            markdown.append(f'## {text}\n')
        elif block_type == 'heading_2':
            text = rich_text_to_markdown(block['heading_2']['rich_text'])
            markdown.append(f'### {text}\n')
        elif block_type == 'heading_3':
            text = rich_text_to_markdown(block['heading_3']['rich_text'])
            markdown.append(f'#### {text}\n')
        # Lists
        elif block_type == 'bulleted_list_item':
            text = rich_text_to_markdown(block['bulleted_list_item']['rich_text'])
            markdown.append(f'- {text}\n')
        elif block_type == 'numbered_list_item':
            text = rich_text_to_markdown(block['numbered_list_item']['rich_text'])
            markdown.append(f'1. {text}\n')
        # Code blocks
        elif block_type == 'code':
            code = rich_text_to_markdown(block['code']['rich_text'])
            language = block['code']['language']
            markdown.append(f'```{language}\n{code}\n```\n')
        # Quotes
        elif block_type == 'quote':
            text = rich_text_to_markdown(block['quote']['rich_text'])
            markdown.append(f'> {text}\n')
        # Images
        elif block_type == 'image':
            image = block['image']
            url = image.get('file', {}).get('url') or \
                  image.get('external', {}).get('url')
            if url:
                if post_dir is not None:
                    try:
                        url = download_image(url, block['id'], post_dir)
                        if images is not None:
                            images.add(url)
                    except Exception as e:
                        if 'file' in image:
                            # Notion-hosted links expire, so don't publish one
                            raise RuntimeError(f'could not download image: {e}')
                        print(f'  ! could not download external image, linking to it instead: {e}')
                caption = rich_text_to_markdown(image.get('caption', []))
                alt_text = caption if caption else 'Image'
                markdown.append(f'![{alt_text}]({url})\n')
        # Divider
        elif block_type == 'divider':
            markdown.append('---\n')
    return '\n'.join(markdown)
def rich_text_to_markdown(rich_text):
    """Convert Notion rich text to markdown formatting"""
    if not rich_text:
        return ''
    result = []
    for text_obj in rich_text:
        text = text_obj['plain_text']
        annotations = text_obj['annotations']
        # Apply markdown formatting
        if annotations['bold']:
            text = f'**{text}**'
        if annotations['italic']:
            text = f'*{text}*'
        if annotations['code']:
            text = f'`{text}`'
        if annotations['strikethrough']:
            text = f'~~{text}~~'
        # Handle links
        if text_obj.get('href'):
            text = f'[{text}]({text_obj["href"]})'
        result.append(text)
    return ''.join(result)
def extract_properties(page):
    """Extract front matter properties from Notion page"""
    props = page['properties']
    # Title
    title_prop = props.get('Name') or props.get('Title')
    title = ''
    if title_prop and title_prop.get('title'):
        title = title_prop['title'][0]['plain_text']
    # Date
    date_prop = props.get('Published Date') or props.get('Date')
    date = datetime.now().isoformat()
    if date_prop and date_prop.get('date'):
        date = date_prop['date']['start']
    # Slug
    slug_prop = props.get('Slug')
    slug = ''
    if slug_prop and slug_prop.get('rich_text'):
        slug = slug_prop['rich_text'][0]['plain_text']
    if not slug:
        # Auto-generate from title
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    # Description
    desc_prop = props.get('Description')
    description = ''
    if desc_prop and desc_prop.get('rich_text'):
        description = desc_prop['rich_text'][0]['plain_text']
    # Tags
    tags_prop = props.get('Tags')
    tags = []
    if tags_prop and tags_prop.get('multi_select'):
        tags = [tag['name'] for tag in tags_prop['multi_select']]
    # Category
    cat_prop = props.get('Category')
    category = 'Uncategorized'
    if cat_prop and cat_prop.get('select'):
        category = cat_prop['select']['name']
    return {
        'title': title,
        'date': date,
        'slug': re.sub(r'[^A-Za-z0-9_-]+', '-', slug).strip('-'),
        'description': description,
        'tags': tags,
        'category': category
    }
def create_hugo_post(page_id, properties, content):
    """Create Hugo markdown file with front matter"""
    slug = properties['slug']
    # Page bundle: content/posts/<slug>/index.md with the post's images beside it
    filename = f"{slug}/index.md"
    filepath = Path(OUTPUT_DIR) / slug / 'index.md'
    # Build front matter
    # json.dumps gives valid YAML strings, so quotes in a title can't break the build
    front_matter = f"""---
title: {json.dumps(properties['title'], ensure_ascii=False)}
date: {properties['date']}
description: {json.dumps(properties['description'], ensure_ascii=False)}
tags: {json.dumps(properties['tags'], ensure_ascii=False)}
categories: {json.dumps([properties['category']], ensure_ascii=False)}
draft: false
notion_id: "{page_id}"
notion_edited: "{properties['edited']}"
---
"""
    # Write file
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(front_matter)
        f.write(content)
    # Remove the old flat file from before posts were bundles, or Hugo sees two pages
    legacy = Path(OUTPUT_DIR) / f'{slug}.md'
    if legacy.exists():
        legacy.unlink()
        print(f'  removed old {legacy.name}')
    print(f'✓ Created: {filename}')
    return filename
def sync():
    """Main sync function"""
    print('🔄 Syncing Notion to Hugo...\n')
    # FORCE_SYNC=1 rebuilds every post; otherwise unchanged pages are skipped
    force = os.environ.get('FORCE_SYNC') == '1'
    try:
        pages = query_database()
    except Exception as e:
        print(f'❌ Error querying database: {e}')
        raise SystemExit(1)
    published = sum(1 for p in pages if page_status(p) == 'Published')
    print(f'Found {len(pages)} pages in Notion, {published} published\n')

    managed = find_managed_posts()
    seen = set()
    synced = skipped = drafted = errors = 0
    for page in pages:
        page_id = page['id']
        seen.add(page_id)
        existing = managed.get(page_id)
        try:
            # No longer Published: keep the file but hide it from the site
            if page_status(page) != 'Published':
                if existing and mark_draft(existing):
                    print(f'⏸ Unpublished: {existing.parent.name}')
                    drafted += 1
                continue

            properties = extract_properties(page)
            if not properties['slug']:
                raise ValueError('page has no title or slug')
            properties['edited'] = page['last_edited_time']
            post_dir = Path(OUTPUT_DIR) / properties['slug']

            # Unchanged since the last sync: nothing to do
            if not force and existing == post_dir / 'index.md':
                front = read_front_matter(existing)
                if front.get('notion_edited') == properties['edited'] and front.get('draft') == 'false':
                    skipped += 1
                    continue

            blocks = get_page_content(page_id)
            images = set()
            content = notion_to_markdown(blocks, post_dir, images)
            # Drop images this post no longer uses
            if post_dir.exists():
                for old in post_dir.glob('image-*'):
                    if old.name not in images:
                        old.unlink()
            create_hugo_post(page_id, properties, content)
            # Slug changed: remove the old copy so the post isn't duplicated
            if existing and existing.parent != post_dir:
                shutil.rmtree(existing.parent)
                print(f'  renamed from {existing.parent.name}')
            synced += 1
        except Exception as e:
            print(f'✗ Error processing page: {e}')
            errors += 1

    # Posts whose Notion page was deleted or archived: hide them too.
    # Skipped when Notion returned nothing at all, which looks more like a
    # permissions problem than someone deleting every post.
    if pages:
        for page_id, path in managed.items():
            if page_id not in seen and mark_draft(path):
                print(f'⏸ Removed from Notion: {path.parent.name}')
                drafted += 1
    elif managed:
        print('⚠ Notion returned no pages; leaving existing posts alone')

    print(f'\n✅ Sync complete!')
    print(f'   Synced: {synced} posts, unchanged: {skipped}, unpublished: {drafted}')
    if errors > 0:
        print(f'   Errors: {errors} posts')
        raise SystemExit(1)


if __name__ == '__main__':
    # Validate environment variables
    if not NOTION_TOKEN:
        print('❌ Error: NOTION_TOKEN not set')
        exit(1)
    if not DATABASE_ID:
        print('❌ Error: NOTION_DATABASE_ID not set')
        exit(1)
    sync()
