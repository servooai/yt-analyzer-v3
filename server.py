"""
YouTube AI Analyzer - Backend Server
ياتستخدم لجلب الترجمة الحقيقية من فيديوهات يوتيوب
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
import re

app = Flask(__name__)
CORS(app)

# إنشاء instance من YouTubeTranscriptApi
ytt_api = YouTubeTranscriptApi()


def extract_video_id(url_or_id):
    """استخراج الـ video ID من رابط يوتيوب"""
    patterns = [
        r'(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, str(url_or_id))
        if match:
            return match.group(1)
    return None


@app.route('/health', methods=['GET'])
def health_check():
    """فحص حالة السيرفر"""
    return jsonify({
        'status': 'ok',
        'message': 'YouTube Analyzer Backend is running!'
    })


@app.route('/transcript', methods=['GET', 'POST'])
def get_transcript():
    """
    جلب الترجمة الكاملة لفيديو يوتيوب
    """
    video_input = request.args.get('video_id') or request.args.get('url', '')

    if not video_input:
        return jsonify({'error': 'لم يتم توفير معرف الفيديو'}), 400

    video_id = extract_video_id(video_input)

    if not video_id:
        return jsonify({'error': 'رابط أو معرف فيديو غير صالح'}), 400

    try:
        transcript = ytt_api.fetch(
            video_id,
            languages=['ar', 'en', 'es', 'de', 'fr', 'pt', 'it']
        )

        formatted_lines = []
        for entry in transcript:
            start_seconds = int(entry.start)
            minutes = start_seconds // 60
            seconds = start_seconds % 60
            text = entry.text.replace('\n', ' ').strip()

            if text:
                formatted_lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

        full_transcript = '\n'.join(formatted_lines)

        return jsonify({
            'success': True,
            'video_id': video_id,
            'transcript': full_transcript
        })

    except Exception as e:
        error_message = str(e)

        if 'No transcripts were found' in error_message:
            return jsonify({
                'error': 'لا توجد ترجمة متاحة لهذا الفيديو',
                'video_id': video_id
            }), 404
        elif 'Video unavailable' in error_message:
            return jsonify({
                'error': 'الفيديو غير متاح أو محذوف',
                'video_id': video_id
            }), 404
        else:
            return jsonify({
                'error': f'حدث خطأ: {error_message}',
                'video_id': video_id
            }), 500


@app.route('/video-info', methods=['GET'])
def get_video_info():
    """جلب معلومات الفيديو باستخدام oEmbed"""
    video_id = request.args.get('video_id')

    if not video_id:
        return jsonify({'error': 'معرف الفيديو مطلوب'}), 400

    try:
        video_id = extract_video_id(video_id)

        import urllib.request
        import json

        oembed_url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'

        with urllib.request.urlopen(oembed_url, timeout=10) as response:
            data = json.loads(response.read().decode())

            return jsonify({
                'success': True,
                'video_id': video_id,
                'title': data.get('title', ''),
                'author': data.get('author_name', ''),
                'thumbnail': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
            })

    except Exception as e:
        return jsonify({
            'error': str(e),
            'video_id': video_id
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
