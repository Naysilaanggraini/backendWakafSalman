MAX_THUMBNAIL_BYTES = 700000


def thumbnail_error(value):
    try:
        size = len(value.encode('utf-8'))
    except UnicodeEncodeError:
        return 'Thumbnail mengandung teks tidak valid'
    if size > MAX_THUMBNAIL_BYTES:
        return f'Thumbnail maksimal {MAX_THUMBNAIL_BYTES} byte UTF-8; ukuran gambar maksimal 512 KB'
    return None
