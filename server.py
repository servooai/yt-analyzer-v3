"""
YouTube AI Analyzer - Backend Server
"""

import os
import re
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# CONFIG
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ============================================
#  HELPERS
# ============================================
def extract_video_id(url_or_id):
    patterns = [
        r'(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for p in patterns:
        m = re.search(p, str(url_or_id))
        if m:
            return m.group(1)
    return None

def ask_ai(prompt, system=None):
    if not client:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.8,
            max_tokens=2000
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

def get_youtube_data(video_id):
    """Get video data from YouTube oEmbed API"""
    try:
        import urllib.request
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return {
            'title': data.get('title', ''),
            'author': data.get('author_name', ''),
            'thumbnail': data.get('thumbnail_url', '')
        }
    except:
        return None

def get_video_stats(video_id):
    """Get video stats from YouTube Data API"""
    if not GOOGLE_API_KEY:
        return {'viewCount': '0', 'likeCount': '0', 'commentCount': '0'}
    try:
        import urllib.request
        url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={GOOGLE_API_KEY}"
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        if data.get('items'):
            item = data['items'][0]
            stats = item.get('statistics', {})
            snippet = item.get('snippet', {})
            return {
                'viewCount': stats.get('viewCount', '0'),
                'likeCount': stats.get('likeCount', '0'),
                'commentCount': stats.get('commentCount', '0'),
                'title': snippet.get('title', ''),
                'channel': snippet.get('channelTitle', '')
            }
    except:
        pass
    return None

def get_transcript(video_id):
    """Get YouTube transcript"""
    try:
        ytt = YouTubeTranscriptApi()
        transcript_list = ytt.fetch(video_id, languages=['en', 'ar', 'es', 'de', 'fr'])
        lines = []
        for entry in transcript_list:
            mins = int(entry.start) // 60
            secs = int(entry.start) % 60
            text = entry.text.replace('\n', ' ').strip()
            if text:
                lines.append(f"[{mins:02d}:{secs:02d}] {text}")
        return '\n'.join(lines) if lines else None
    except:
        return None

# ============================================
#  ROUTES
# ============================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'ai': bool(client),
        'google': bool(GOOGLE_API_KEY)
    })

@app.route('/video', methods=['GET'])
def video():
    """Get video info and stats"""
    video_id = request.args.get('video_id', '')
    video_id = extract_video_id(video_id)
    if not video_id:
        return jsonify({'error': 'Invalid video ID'}), 400

    # Get basic info
    info = get_youtube_data(video_id)
    if not info:
        return jsonify({'error': 'Video not found'}), 404

    # Get stats
    stats = get_video_stats(video_id)
    if stats:
        info.update(stats)

    return jsonify({'success': True, 'video': info})

@app.route('/transcript', methods=['GET'])
def transcript():
    video_id = request.args.get('video_id', '')
    video_id = extract_video_id(video_id)
    if not video_id:
        return jsonify({'error': 'Invalid video ID'}), 400

    transcript = get_transcript(video_id)
    if transcript:
        return jsonify({'success': True, 'transcript': transcript})

    return jsonify({'error': 'No transcript available'}), 404

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    tool = data.get('tool', '')
    title = data.get('title', '') or data.get('video_title', '')
    channel = data.get('channel', '') or data.get('video_channel', '')
    views = data.get('views', 0) or data.get('video_views', 0)
    transcript = data.get('transcript', '')[:3000]
    video_id = data.get('video_id', '')

    # ============================================
    #  PROMPTS - ENGLISH
    # ============================================
    prompts = {
        'transcript': f"""You are a YouTube content analyst. Analyze this video:

VIDEO TITLE: {title}
CHANNEL: {channel}
VIEWS: {views}
{'-' * 40}
VIDEO TRANSCRIPT (if available):
{transcript if transcript else 'No transcript available. Analyze based on title only.'}
{'-' * 40}

Generate REAL content. Do NOT use placeholder text like "topic 1" or "point 1".
Write in English. Return valid JSON:

{{
    "fullScript": "Actual transcript text with timestamps - write out real content",
    "mainTopics": ["Real specific topic 1", "Real specific topic 2", "Real specific topic 3"],
    "keyPoints": ["Real key point 1", "Real key point 2", "Real key point 3", "Real key point 4"],
    "hookUsed": "Real description of how the video starts"
}}

JSON ONLY. No markdown. No text before or after.""",

        'hook': f"""You are a YouTube hook expert. Analyze the opening of this video:

TITLE: {title}
CHANNEL: {channel}
VIEWS: {views}
{'-' * 40}
VIDEO CONTENT:
{transcript[:1500] if transcript else 'No transcript. Analyze based on title.'}
{'-' * 40}

Generate REAL insights. Do NOT use placeholder text like "hook 1" or "reason 1".
Write in English. Return valid JSON:

{{
    "hookAnalysis": "Detailed real analysis of the opening hook - what words are used, what psychological triggers, how it grabs attention",
    "whyViral": ["Real reason video went viral 1", "Real reason 2", "Real reason 3", "Real reason 4", "Real reason 5"],
    "suggestedHooks": ["Real hook suggestion 1", "Real hook suggestion 2", "Real hook suggestion 3", "Real hook suggestion 4", "Real hook suggestion 5"]
}}

JSON ONLY. No text before or after.""",

        'script': f"""You are a YouTube script writer. Create a similar script:

TITLE: {title}
CHANNEL: {channel}
{'-' * 40}
VIDEO CONTENT:
{transcript[:1500] if transcript else 'No transcript. Analyze based on title.'}
{'-' * 40}

Generate REAL script. Do NOT use placeholder text.
Write in English. Return valid JSON:

{{
    "newHook": "Real strong hook - exact words to say in first 5 seconds",
    "newScript": "Real script outline - write actual content, not placeholders. Include timing and key moments",
    "keyMoments": ["Real key moment 1", "Real key moment 2", "Real key moment 3", "Real key moment 4"]
}}

JSON ONLY.""",

        'titles': f"""You are a YouTube SEO expert. Generate 10 click-worthy titles:

VIDEO TITLE: {title}
CHANNEL: {channel}
VIEWS: {views}
{'-' * 40}
CONTENT SUMMARY:
{transcript[:800] if transcript else 'No transcript. Use your creativity.'}
{'-' * 40}

Requirements:
- Each title under 60 characters
- Different from original title
- Click-worthy, use psychological triggers
- Real titles, not placeholders

Return JSON array of 10 strings:
["Real Title 1", "Real Title 2", "Real Title 3", "Real Title 4", "Real Title 5", "Real Title 6", "Real Title 7", "Real Title 8", "Real Title 9", "Real Title 10"]

JSON ONLY. No text before or after.""",

        'desc': f"""You are a YouTube description writer. Create SEO description:

TITLE: {title}
CHANNEL: {channel}
{'-' * 40}
CONTENT:
{transcript[:1000] if transcript else 'No transcript.'}
{'-' * 40}

Write in English. Return JSON:
{{
    "description": "Real engaging description 150-250 words - include key points, timestamps if relevant, call to action. NOT placeholder text.",
    "hashtags": ["#realhashtag1", "#realhashtag2", "#realhashtag3", "#realhashtag4", "#realhashtag5", "#realhashtag6"]
}}

JSON ONLY."""
    }

    if tool not in prompts:
        return jsonify({'error': 'Invalid tool'}), 400

    if not client:
        return jsonify({'error': 'OpenAI API not configured'}), 500

    result = ask_ai(prompts[tool])
    if not result or result.startswith('Error:'):
        return jsonify({'error': result or 'AI request failed'}), 500

    try:
        clean = re.sub(r'```json\s*', '', result, flags=re.IGNORECASE)
        clean = re.sub(r'```\s*', '', clean)
        parsed = json.loads(clean.strip())
        return jsonify({'success': True, 'result': parsed})
    except:
        return jsonify({'success': True, 'result': result})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
