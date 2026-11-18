"""Store Markdown images separately so editors and backups keep compact references."""
import base64
import binascii
import hashlib
import re

MAX_IMAGE_BYTES = 10 * 1024 * 1024
INLINE_IMAGE = re.compile(r'data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)')
IMAGE_ID = re.compile(r'^[a-f0-9]{64}$')


def image_type(content):
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if content.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        return 'image/webp'
    raise ValueError('支持 PNG、JPEG、WebP 或 GIF 图片。')


def save_image(connection, content):
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError('单张图片不能超过 10 MB。')
    content_type = image_type(content)
    image_id = hashlib.sha256(content).hexdigest()
    connection.execute('INSERT OR IGNORE INTO images (id, content_type, content) VALUES (?, ?, ?)',
                       (image_id, content_type, content))
    return '/api/images/' + image_id


def compact_images(connection, markdown):
    def replace(match):
        try:
            content = base64.b64decode(match[2], validate=True)
            return save_image(connection, content)
        except (ValueError, binascii.Error):
            # Preserve old Markdown if an inline image is malformed or unsupported.
            return match[0]
    return INLINE_IMAGE.sub(replace, markdown)


def export_images(connection):
    return [{'id': row['id'], 'content_type': row['content_type'],
             'content': base64.b64encode(row['content']).decode('ascii')}
            for row in connection.execute('SELECT * FROM images ORDER BY id')]


def import_images(connection, images):
    for image in images:
        try:
            content = base64.b64decode(image['content'], validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError('备份中的图片数据无效') from error
        url = save_image(connection, content)
        if url != '/api/images/' + image['id'] or image_type(content) != image['content_type']:
            raise ValueError('备份中的图片数据无效')
