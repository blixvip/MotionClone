"""Private local bookmarks. Links are validated, never fetched by the server."""
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date as CalendarDate
from urllib.parse import urlsplit
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ConfigDict, Field, field_validator, model_validator

from .models import Strict


def canonical_url(value):
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        host = (parsed.hostname or '').lower()
        if host in ('x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com'):
            match = re.fullmatch(r'/([A-Za-z0-9_]{1,30})/status/(\d+)(?:/(?:video|photo)/\d+)?/?', parsed.path)
            if match:
                author, ident = match.groups()
                return f'https://x.com/{author}/status/{ident}', 'x', '@' + author, 'x:' + ident
        if host in ('threads.net', 'www.threads.net', 'threads.com', 'www.threads.com'):
            match = re.fullmatch(r'/@([A-Za-z0-9_.]{1,64})/post/([A-Za-z0-9_-]{1,100})/?', parsed.path)
            if match:
                author, ident = match.groups()
                return f'https://www.threads.com/@{author}/post/{ident}', 'threads', '@' + author, 'threads:' + ident
    except ValueError:
        pass
    raise ValueError('Paste a link to an X / Twitter post or a Threads post.')


class PostFields(Strict):
    title: str = Field(default='', max_length=180)
    text: str = Field(default='', max_length=12000)
    notes: str = Field(default='', max_length=3000)
    tags: list[str] = Field(default_factory=list, max_length=15)

    @field_validator('tags')
    @classmethod
    def tidy_tags(cls, values):
        result, seen = [], set()
        for value in values:
            value = value.strip().lstrip('#')
            if len(value) > 36:
                raise ValueError('Keep each tag under 37 characters.')
            if value and value.casefold() not in seen:
                seen.add(value.casefold()); result.append(value)
        return result


class NewPost(PostFields):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        return canonical_url(value)[0]


class EditPost(PostFields):
    favorite: bool = False
    archived: bool = False


class RestoredPost(NewPost):
    model_config = ConfigDict(extra='ignore')
    favorite: bool = False
    archived: bool = False
    created: float | None = Field(default=None, gt=0, le=32503680000)


class Composition(PostFields):
    model_config = ConfigDict(extra='ignore')
    platform: Literal['linkedin', 'threads', 'x', 'youtube'] = 'x'
    status: Literal['draft', 'planned', 'published'] = 'draft'
    date: CalendarDate | None = None
    time: str = Field(default='', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$|^$')
    favorite: bool = False
    archived: bool = False

    @model_validator(mode='after')
    def valid_plan(self):
        if not any(value.strip() for value in (self.title, self.text, self.notes)):
            raise ValueError('Add a title, post text, or notes before saving.')
        if self.status == 'planned' and not self.date:
            raise ValueError('Choose a date for a planned post.')
        if self.time and not self.date:
            raise ValueError('Choose a date before adding a time.')
        return self


class RestoredComposition(Composition):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    created: float = Field(gt=0, le=32503680000)
    updated: float = Field(gt=0, le=32503680000)


class Backup(Strict):
    version: Literal[1, 2]
    exported: str = Field(default='', max_length=100)
    posts: list[RestoredPost] = Field(max_length=5000)
    compositions: list[RestoredComposition] = Field(default_factory=list, max_length=5000)


def install(app, host):
    @contextmanager
    def database():
        host.DATA.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(host.DATA / 'posts.sqlite3', timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                connection.execute('''CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL, platform TEXT NOT NULL, author TEXT NOT NULL,
                    title TEXT NOT NULL, text TEXT NOT NULL, notes TEXT NOT NULL, tags TEXT NOT NULL,
                    favorite INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL, updated REAL NOT NULL)''')
                connection.execute('CREATE TABLE IF NOT EXISTS compositions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
                yield connection
        except sqlite3.Error:
            raise HTTPException(503, 'Your post library could not be saved or loaded. Please retry.') from None
        finally:
            connection.close()

    def public(row):
        value = dict(row)
        value.pop('identity')
        value['tags'] = json.loads(value['tags'])
        value['favorite'] = bool(value['favorite'])
        value['archived'] = bool(value['archived'])
        return value

    @app.get('/posts', response_class=HTMLResponse)
    def page():
        return (host.ROOT / 'web/posts.html').read_text(encoding='utf-8')

    @app.get('/api/posts')
    def list_posts():
        with database() as db:
            return [public(row) for row in db.execute('SELECT * FROM posts ORDER BY created DESC, id')]

    @app.get('/api/compositions')
    def list_compositions():
        with database() as db:
            return [json.loads(row['payload']) for row in db.execute('SELECT payload FROM compositions ORDER BY rowid DESC')]

    def composition_values(post):
        values = post.model_dump(mode='json')
        for key in ('title', 'text', 'notes'):
            values[key] = values[key].strip()
        return values

    @app.post('/api/compositions', status_code=201)
    def create_composition(post: Composition):
        now = time.time()
        values = {**composition_values(post), 'id':uuid.uuid4().hex, 'created':now, 'updated':now}
        with database() as db:
            db.execute('INSERT INTO compositions (id,payload) VALUES (?,?)', (values['id'], json.dumps(values)))
        return values

    @app.put('/api/compositions/{ident}')
    def update_composition(ident: str, post: Composition):
        with database() as db:
            row = db.execute('SELECT payload FROM compositions WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise HTTPException(404, 'Draft not found.')
            original = json.loads(row['payload'])
            values = {**composition_values(post), 'id':ident, 'created':original['created'], 'updated':time.time()}
            db.execute('UPDATE compositions SET payload=? WHERE id=?', (json.dumps(values), ident))
            return values

    @app.post('/api/posts')
    def save_post(post: NewPost):
        url, platform, author, identity = canonical_url(post.url)
        now = time.time()
        with database() as db:
            cursor = db.execute('''INSERT INTO posts
                (id,identity,url,platform,author,title,text,notes,tags,created,updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity) DO NOTHING''',
                (uuid.uuid4().hex[:12], identity, url, platform, author, post.title.strip(),
                 post.text.strip(), post.notes.strip(), json.dumps(post.tags), now, now))
            inserted = cursor.rowcount == 1
            row = db.execute('SELECT * FROM posts WHERE identity=?', (identity,)).fetchone()
            return JSONResponse({'post': public(row), 'duplicate': not inserted}, status_code=201 if inserted else 200)

    @app.patch('/api/posts/{ident}')
    def update_post(ident: str, changes: EditPost):
        values = changes.model_dump(exclude_unset=True)
        with database() as db:
            row = db.execute('SELECT * FROM posts WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise HTTPException(404, 'Saved post not found.')
            if values:
                for key in ('title', 'text', 'notes'):
                    if key in values: values[key] = values[key].strip()
                if 'tags' in values: values['tags'] = json.dumps(values['tags'])
                values['updated'] = time.time()
                # Column names come exclusively from the validated model.
                db.execute('UPDATE posts SET ' + ','.join(key + '=?' for key in values) + ' WHERE id=?', [*values.values(), ident])
            return public(db.execute('SELECT * FROM posts WHERE id=?', (ident,)).fetchone())

    @app.post('/api/posts/import')
    def import_posts(backup: Backup):
        now, imported = time.time(), 0
        with database() as db:
            for post in backup.posts:
                url, platform, author, identity = canonical_url(post.url)
                cursor = db.execute('''INSERT INTO posts
                    (id,identity,url,platform,author,title,text,notes,tags,favorite,archived,created,updated)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity) DO NOTHING''',
                    (uuid.uuid4().hex[:12], identity, url, platform, author, post.title.strip(),
                     post.text.strip(), post.notes.strip(), json.dumps(post.tags), post.favorite,
                     post.archived, post.created or now, now))
                imported += cursor.rowcount
            for post in backup.compositions:
                values = composition_values(post)
                cursor = db.execute('INSERT INTO compositions (id,payload) VALUES (?,?) ON CONFLICT(id) DO NOTHING', (post.id, json.dumps(values)))
                imported += cursor.rowcount
        return {'imported':imported, 'skipped':len(backup.posts) + len(backup.compositions) - imported}
