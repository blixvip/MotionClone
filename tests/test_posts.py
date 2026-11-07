from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.posts import install


@pytest.fixture
def posts(tmp_path):
    host = SimpleNamespace(DATA=tmp_path, ROOT=tmp_path)
    app = FastAPI()
    install(app, host)
    return TestClient(app), host


def test_save_persists_and_duplicate_does_not_replace_notes(posts):
    client, host = posts
    first = client.post('/api/posts', json={'url': 'https://twitter.com/kai/status/123?s=20', 'notes': 'Keep this', 'tags': ['Motion', 'motion']})
    assert first.status_code == 201
    item = first.json()['post']
    assert item['url'] == 'https://x.com/kai/status/123'
    assert item['tags'] == ['Motion']
    duplicate = client.post('/api/posts', json={'url': 'https://x.com/other/status/123/video/1'})
    assert duplicate.status_code == 200 and duplicate.json()['duplicate']
    assert duplicate.json()['post']['notes'] == 'Keep this'
    fresh = FastAPI(); install(fresh, host)
    assert TestClient(fresh).get('/api/posts').json()[0]['id'] == item['id']


def test_threads_domains_and_thread_root_are_deduplicated(posts):
    client, _ = posts
    a = client.post('/api/posts', json={'url': 'https://www.threads.net/@kai/post/AbC_12?x=1'}).json()['post']
    b = client.post('/api/posts', json={'url': 'https://www.threads.com/@kai/post/AbC_12'}).json()
    assert a['platform'] == 'threads' and a['author'] == '@kai'
    assert b['post']['id'] == a['id'] and b['duplicate']


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://x.com.evil.test/kai/status/123', 'https://x.com@evil.test/kai/status/123', 'http://127.0.0.1/post/123', 'https://x.com/kai', 'https://threads.com/@kai', 'https://x.com:444/kai/status/123'])
def test_rejects_non_post_and_unsafe_links(posts, url):
    client, _ = posts
    assert client.post('/api/posts', json={'url': url}).status_code == 422
    assert client.get('/api/posts').json() == []


def test_edit_archive_restore_and_null_validation(posts):
    client, _ = posts
    item = client.post('/api/posts', json={'url': 'https://x.com/kai/status/456'}).json()['post']
    path = '/api/posts/' + item['id']
    edit = client.patch(path, json={'title': '<script>plain text</script>', 'text': 'A whole thread\nSecond thought', 'favorite': True, 'archived': True})
    assert edit.status_code == 200 and edit.json()['archived']
    assert client.patch(path, json={'archived': False}).json()['favorite']
    assert client.patch(path, json={'notes': None}).status_code == 422
    assert client.patch(path, json={'url': 'https://evil.test'}).status_code == 422
    assert client.patch('/api/posts/missing', json={'title': 'x'}).status_code == 404


def test_concurrent_duplicate_saves_are_one_record(posts):
    client, _ = posts
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: client.post('/api/posts', json={'url': 'https://x.com/kai/status/987'}), range(3)))
    assert sorted(r.status_code for r in responses) == [200, 200, 201]
    assert len(client.get('/api/posts').json()) == 1


def test_main_app_protects_library_writes(tmp_path, monkeypatch):
    import app.server as server
    monkeypatch.setattr(server, 'DATA', tmp_path)
    client = TestClient(server.app)
    payload = {'url': 'https://x.com/kai/status/123'}
    assert client.post('/api/posts', json=payload).status_code == 403
    headers = {'X-Frameforge-Token': server.TOKEN}
    assert client.post('/api/posts', json=payload, headers={**headers, 'Origin':'https://evil.test'}).status_code == 403
    assert client.post('/api/posts', json=payload, headers=headers).status_code == 201
    assert client.get('/posts').status_code == 200


def test_restore_merges_without_overwriting_and_validates_before_writing(posts):
    client, _ = posts
    existing = client.post('/api/posts', json={'url':'https://x.com/kai/status/123', 'notes':'Keep my newer note'}).json()['post']
    backup = {'version':1, 'posts':[
        {**existing, 'notes':'Older note'},
        {'url':'https://threads.net/@studio/post/Backup_1', 'title':'Restored find', 'favorite':True, 'archived':True, 'created':1700000000},
    ]}
    response = client.post('/api/posts/import', json=backup)
    assert response.status_code == 200 and response.json() == {'imported':1, 'skipped':1}
    saved = client.get('/api/posts').json()
    assert len(saved) == 2
    assert next(p for p in saved if p['id'] == existing['id'])['notes'] == 'Keep my newer note'
    recovered = next(p for p in saved if p['platform'] == 'threads')
    assert recovered['favorite'] and recovered['archived'] and recovered['created'] == 1700000000
    invalid = {'version':1, 'posts':[{'url':'https://x.com/kai/status/999'}, {'url':'javascript:alert(1)'}]}
    assert client.post('/api/posts/import', json=invalid).status_code == 422
    assert len(client.get('/api/posts').json()) == 2
    assert client.post('/api/posts/import', json={'version':3, 'posts':[]}).status_code == 422


def test_standalone_site_boundary_and_navigation():
    import app.posts_site as standalone
    client = TestClient(standalone.app)
    assert 'Post Schedule' in client.get('/posts').text
    assert client.get('/', follow_redirects=False).headers['location'] == '/posts'
    assert client.get('/?workspace=1', follow_redirects=False).headers['location'].endswith('4319/?workspace=1')
    assert client.post('/api/posts', json={'url':'https://x.com/kai/status/123'}).status_code == 403
    assert client.get('/api/status', headers={'host':'evil.test'}).status_code == 403
    assert client.post('/api/posts', headers={'X-Frameforge-Token':standalone.TOKEN, 'Origin':'https://evil.test'}, json={}).status_code == 403
