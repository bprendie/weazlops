"""Publish an existing paired build into the operator library and native USB catalog."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from app.firmware_catalog import NAMES, validate_bundle

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('release', type=Path)
parser.add_argument('--library', type=Path, default=BASE/'Firmware')
args = parser.parse_args()
source = args.release
manifest = json.loads((source/'esp32s3/manifest.json').read_text())
product, version = manifest['product'], manifest['version']
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', version):
    raise SystemExit('Invalid release version')
title = f'{NAMES[product]} {version}'
catalog = BASE/'.runtime/firmware'
catalog.mkdir(exist_ok=True, parents=True)
args.library.mkdir(exist_ok=True, parents=True)
destination = catalog/f'{product}-{version}'
archive = args.library/f'{title} (ESP32-S3 and ESP32-C5).zip'
with tempfile.TemporaryDirectory(dir=catalog) as tmp:
    work = Path(tmp)
    bundle = work/'bundle.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
        for chip in ('esp32s3','esp32c5'):
            folder = source/chip
            m = json.loads((folder/'manifest.json').read_text())
            names = [image['file'] for image in m['images']]
            if any(Path(n).name != n for n in names):
                raise ValueError('Invalid image name')
            for name in ['manifest.json', *names]:
                z.write(folder/name, f'{chip}/{name}')
        for name in ('README.txt','corresponding-source.zip'):
            z.write(source/name, name)
    validate_bundle(bundle, work/'release')
    if destination.exists() or archive.exists():
        raise SystemExit(f'Release already exists: {title}')
    with tempfile.NamedTemporaryFile(dir=args.library,delete=False) as f:
        pending = Path(f.name)
        with bundle.open('rb') as reader:
            shutil.copyfileobj(reader,f)
    try:
        os.link(pending,archive)
        try:
            (work/'release').rename(destination)
        except BaseException:
            archive.unlink()
            raise
    finally:
        pending.unlink()
    print(archive)
