import base64
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from api.main import create_app

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/L9sAAAAASUVORK5CYII=')


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'library.db'
        self.context = TestClient(create_app(self.database))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.directory.cleanup()

    def test_upload_deduplicates_and_uses_short_url(self):
        first = self.client.post('/api/images', content=PNG)
        self.assertEqual(first.status_code, 201, first.text)
        url = first.json()['url']
        self.assertLess(len(url), 80)
        self.assertEqual(self.client.post('/api/images', content=PNG).json()['url'], url)
        image = self.client.get(url)
        self.assertEqual(image.content, PNG)
        self.assertEqual(image.headers['content-type'], 'image/png')
        self.assertEqual(len(self.client.get('/api/library/backup').json()['images']), 1)

    def test_large_image_and_invalid_content_are_rejected(self):
        self.assertEqual(self.client.post('/api/images', content=b'<svg>bad</svg>').status_code, 400)
        large = PNG + b'x' * (2 * 1024 * 1024)
        self.assertEqual(self.client.post('/api/images', content=large).status_code, 201)
        self.assertEqual(self.client.post('/api/images', content=PNG + b'x' * (10 * 1024 * 1024)).status_code, 413)
        self.assertEqual(self.client.get('/api/images/unknown').status_code, 404)

    def test_images_and_references_survive_restore_and_old_backups(self):
        url = self.client.post('/api/images', content=PNG).json()['url']
        task = self.client.post('/api/tasks', json={'title': 'Image task', 'description': f'![image]({url})'}).json()
        self.client.patch(f"/api/tasks/{task['id']}/progress", json={'notes': f'![notes]({url})'})
        backup = self.client.get('/api/library/backup').json()
        with TestClient(create_app(Path(self.directory.name) / 'restored.db')) as target:
            response = target.post('/api/library/restore', json=backup)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(target.get(url).content, PNG)
            self.assertIn(url, target.get(f"/api/tasks/{task['id']}").json()['progress']['notes'])
        old_backup = copy.deepcopy(backup)
        old_backup.pop('images')
        self.assertEqual(self.client.post('/api/library/restore', json=old_backup).status_code, 200)
        backup['images'][0]['id'] = '0' * 64
        self.assertEqual(self.client.post('/api/library/restore', json=backup).status_code, 400)

    def test_legacy_inline_images_are_compacted_on_save_and_startup(self):
        inline = '![image](data:image/png;base64,' + base64.b64encode(PNG).decode() + ')'
        compacted = self.client.post('/api/images/compact', json={'markdown': inline}).json()['markdown']
        self.assertNotIn('base64', compacted)
        task = self.client.post('/api/tasks', json={'title': 'Legacy image', 'description': inline}).json()
        self.assertEqual(task['description'], compacted)
        with sqlite3.connect(self.database) as connection:
            connection.execute('UPDATE custom_tasks SET description = ? WHERE id = ?', (inline, task['id']))
        with TestClient(create_app(self.database)) as restarted:
            self.assertEqual(restarted.get(f"/api/tasks/{task['id']}").json()['description'], compacted)

    def test_health_identifies_loaded_backend(self):
        health = self.client.get('/api/health').json()
        self.assertEqual(health['api_version'], 3)
        self.assertEqual(len(health['backend_revision']), 16)
        self.assertGreater(health['pid'], 0)
