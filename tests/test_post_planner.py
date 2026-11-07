from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.posts import install


@pytest.fixture
def planner(tmp_path):
    host = SimpleNamespace(DATA=tmp_path, ROOT=tmp_path)
    app = FastAPI()
    install(app, host)
    return TestClient(app), host


@pytest.mark.parametrize('platform', ['linkedin', 'threads', 'x', 'youtube'])
def test_compose_without_link_and_reopen(planner, platform):
    client, host = planner
    response = client.post('/api/compositions', json={'platform': platform, 'text': 'My next post', 'date': '2026-10-06'})
    assert response.status_code == 201
    post = response.json()
    assert post['status'] == 'draft' and post['date'] == '2026-10-06'
    app = FastAPI(); install(app, host)
    assert TestClient(app).get('/api/compositions').json() == [post]
    response = client.put('/api/compositions/' + post['id'], json={**post, 'status': 'planned', 'date': '2026-11-02', 'time': '09:30', 'text': 'Revised copy'})
    assert response.status_code == 200
    assert response.json()['text'] == 'Revised copy'
    assert response.json()['date'] == '2026-11-02'


def test_invalid_plans_do_not_write(planner):
    client, _ = planner
    for values in [{'platform': 'unsupported', 'text': 'x'}, {'text': '   '}, {'text':'x', 'status':'planned'}, {'text':'x', 'date':'2026-02-30'}, {'text':'x', 'time':'25:00'}, {'text':'x', 'date':'2026-01-01', 'status':'auto-post'}]:
        assert client.post('/api/compositions', json=values).status_code == 422
    assert client.get('/api/compositions').json() == []


def test_backup_restores_drafts_and_bookmarks_without_overwrite(planner):
    client, host = planner
    draft = client.post('/api/compositions', json={'platform':'youtube', 'title':'Video idea', 'text':'Community post', 'status':'draft'}).json()
    bookmark = client.post('/api/posts', json={'url':'https://x.com/kai/status/123'}).json()['post']
    backup = {'version':2, 'posts':[bookmark], 'compositions':[draft]}
    assert client.post('/api/posts/import', json=backup).json() == {'imported':0, 'skipped':2}
    app = FastAPI(); install(app, SimpleNamespace(DATA=host.DATA / 'restored', ROOT=host.ROOT))
    restored = TestClient(app)
    assert restored.post('/api/posts/import', json=backup).json() == {'imported':2, 'skipped':0}
    assert restored.get('/api/compositions').json()[0]['text'] == 'Community post'
    assert restored.get('/api/posts').json()[0]['url'] == bookmark['url']
    assert client.put('/api/compositions/missing', json={'text':'x'}).status_code == 404
