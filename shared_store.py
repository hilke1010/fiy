# -*- coding: utf-8 -*-
"""Yerel ağdaki Streamlit oturumları için tek, kalıcı, sürümlü Excel kaynağı.

- Dosya doğrulanmadan asla güncel kaynak değişmez.
- Yüklemede değişmez SHA-256 adlı dosya, ardından atomik manifest güncellemesi.
- Oturumlardan bağımsızdır; ağ paylaştırma değil, aynı sunucuda dosya paylaşımıdır.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

from engine import ingest

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'shared_data'
MANIFEST = DATA_DIR / 'current.json'
ALLOWED = {'.xlsx', '.xls', '.csv'}
LOCAL_NAMES = ('fiyat.xlsx', 'fiyat.xls', 'fiyat.csv')


def _local_info():
    """app.py ile aynı klasöre konan fiyat.xlsx dosyasını otomatik kaynak say.

    Dosya zaman/byte uzunluğu okunur, 150 bin satır her istek için tekrar
    taranmaz. Kaydetme sonrası mtime değiştiğinde tüm istemciler yeni sürüme geçer.
    """
    for name in LOCAL_NAMES:
        path = ROOT / name
        try:
            st = path.stat()
            if st.st_size == 0:
                continue
            # Buradaki digest yalnız cache sürüm anahtarıdır, içeriğin SHA256'sı
            # değildir. Yerel dosya yalnız belirtilen güvenilir dizinden okunur.
            signature = f'{path.resolve()}|{st.st_size}|{st.st_mtime_ns}'
            return {'sha256': sha256(signature.encode('utf8')).hexdigest(),
                    'extension': path.suffix.lower(), 'original_name': path.name,
                    'path': str(path), 'mode': 'local', 'modified_at': st.st_mtime,
                    'saved_at': datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec='seconds'),
                    'valid_rows': None}
        except OSError:
            continue
    return None


def current_info(folder=None):
    """Son kaydedilen kaynak: yerel fiyat.xlsx veya webden yayımlanan Excel.

    En son yazılan dosya kazanır; salt manifest kontrolü hafiftir.
    """
    custom_folder = folder is not None
    folder = Path(folder) if custom_folder else DATA_DIR
    manifest = folder / 'current.json'
    published = None
    try:
        m = json.loads(manifest.read_text(encoding='utf-8'))
        digest = m['sha256']
        ext = m['extension']
        if re.fullmatch(r'[0-9a-f]{64}', digest) and ext in ALLOWED:
            filepath = folder / f'prices_{digest}{ext}'
            if filepath.is_file():
                published = {**m, 'path': str(filepath), 'mode': 'published'}
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
        pass
    if custom_folder:
        return published
    local = _local_info()
    if local is None:
        return published
    if published is None:
        return local
    try:
        # Eski formatlı manifest için saved_at üzerinden geri uyumluluk.
        published_time = float(published.get('published_at',
                datetime.fromisoformat(published['saved_at']).timestamp()))
    except (KeyError,TypeError,ValueError):
        published_time = 0.0
    return local if local['modified_at'] >= published_time else published


def _atomic_bytes(destination: Path, raw: bytes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(destination.parent), prefix='.upload_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as fout:
            fout.write(raw)
            fout.flush()
            os.fsync(fout.fileno())
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def publish(raw: bytes, filename: str, folder=None):
    """Excel'i doğrula ve tüm oturumlar için yayımla; önceki dosyayı hata halinde koru."""
    folder = Path(folder) if folder else DATA_DIR
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError('Yalnız XLSX, XLS ve CSV desteklenmektedir.')
    if not raw:
        raise ValueError('Dosya boş.')
    if len(raw) > 200 * 1024 * 1024:
        raise ValueError('Dosya 200 MB yükleme sınırını aşmaktadır.')
    clean, quality = ingest(raw, filename)
    if clean.empty:
        raise ValueError('Dosyada analiz edilecek geçerli satır bulunamadı.')
    digest = sha256(raw).hexdigest()
    outfile = folder / f'prices_{digest}{suffix}'
    if not outfile.exists():
        _atomic_bytes(outfile, raw)
    info = {
        'sha256': digest,
        'extension': suffix,
        'original_name': Path(filename).name,
        'saved_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'published_at': datetime.now().timestamp(),
        'valid_rows': int(len(clean)),
        'raw_rows': int(quality['ham_satir']),
    }
    _atomic_bytes(folder / 'current.json', json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8'))
    return current_info(folder)


def read_source(info):
    if not info:
        raise ValueError('Henüz ortak Excel dosyası yok.')
    source_path = Path(info['path'])
    raw = source_path.read_bytes()
    # Yerel fiyat.xlsx sürüm bilgisi (dosya yolu + boyut + mtime) üzerinden izlenir.
    # Yayımlanan Excel'in sürüm bilgisi ise gerçek dosya içeriğinin SHA-256 değeridir.
    if info.get('mode') == 'local':
        # Yerel kaynak yalnız uygulama klasöründe olmalı.
        if source_path.resolve().parent != ROOT.resolve() or source_path.name not in LOCAL_NAMES:
            raise ValueError('Yerel Excel yolu uygulama klasörü dışında; fiyat.xlsx konumunu kontrol edin.')
    elif sha256(raw).hexdigest() != info['sha256']:
        raise ValueError('Yayımlanan Excel dosyası doğrulanamadı; yönetici olarak yeniden yükleyin.')
    return ingest(raw, info['original_name'])
