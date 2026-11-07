import threading
from urllib.parse import urlparse

import pytest
from yt_dlp import YoutubeDL

from app import media


@pytest.mark.parametrize('split', [True, False])
def test_imports_separate_or_combined_streams(tmp_path, monkeypatch, split):
    destination = tmp_path / 'input.bin'
    monkeypatch.setattr(media, 'validate_url', urlparse)

    def run_download(command, **kwargs):
        video = {'format_id': 'video', 'ext': 'mp4', 'height': 1080,
                 'vcodec': 'avc1', 'acodec': 'none', 'url': 'https://example.com/video'}
        audio = {'format_id': 'audio', 'ext': 'm4a', 'vcodec': 'none',
                 'acodec': 'aac', 'url': 'https://example.com/audio'}
        combined = {**video, 'format_id': 'combined', 'acodec': 'aac'}
        with YoutubeDL({'quiet': True}) as downloader:
            select = downloader.build_format_selector(command[command.index('-f') + 1])
            formats = list(select({'formats': [audio, video] if split else [combined],
                                   'has_merged_format': not split, 'incomplete_formats': False}))
        assert len(formats) == 1
        if split:
            assert len(formats[0]['requested_formats']) == 2
            destination.with_name(destination.name + '.mkv').write_bytes(b'merged video and audio')
        else:
            assert formats[0]['acodec'] == 'aac'
            destination.write_bytes(b'combined video and audio')

    monkeypatch.setattr(media, 'run', run_download)
    media.download('https://www.youtube.com/watch?v=example', destination,
                   threading.Event(), lambda *args: None)
    assert destination.is_file()
    assert b'video and audio' in destination.read_bytes()
