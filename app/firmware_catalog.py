"""Validate paired firmware bundles and publish immutable catalog entries."""
import errno
import hashlib
import json
from pathlib import Path
import re
import shutil
from struct import error as StructError
from zlib import error as ZlibError
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

NAMES = {'weazlghost': 'WeazlGhost', 'weazlghost-xl': 'WeazlGhost XL', 'ghost-drop': 'GhostDrop'}


def validate_bundle(bundle, output):
    from backend.releases import validate_release
    from esptool.util import FatalError

    try:
        with ZipFile(bundle) as archive:
            manifests = [item for item in archive.infolist()
                         if Path(item.filename).name == 'manifest.json'
                         and Path(item.filename).parent.name == 'esp32s3']
            if len(manifests) != 1 or manifests[0].file_size > 65536:
                raise ValueError('The ZIP needs one ESP32-S3 and one ESP32-C5 manifest.')
            manifest = json.loads(archive.read(manifests[0]))
        product, version = manifest['product'], manifest['version']
        if product not in NAMES or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', version):
            raise ValueError('The manifest needs a supported device model and a release version.')
        targets = validate_release(bundle, product, version, output)
        if any(not isinstance(m.get('firmware_version'), str) or not re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9._+-]{0,79}', m['firmware_version']) for m in targets.values()):
            raise ValueError('Both targets need a running firmware version.')
    except (BadZipFile, FatalError, KeyError, TypeError, AttributeError, RuntimeError, EOFError, OverflowError, StructError, ZlibError) as exc:
        raise ValueError('Invalid firmware ZIP. Choose a complete packaged S3 and C5 release.') from exc
    entry = {
        'id': f'{product}-{version}',
        'name': f'{NAMES[product]} {version}',
        'product': product,
        'version': version,
        'targets': {chip: hashlib.sha256((output/chip/'manifest.json').read_bytes()).hexdigest()
                    for chip in targets},
    }
    (output/'entry.json').write_text(json.dumps(entry, indent=2))
    return entry


def import_bundle(bundle, catalog):
    catalog.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=catalog, prefix='tmp-import-') as temporary:
        stage = Path(temporary)/'release'
        entry = validate_bundle(bundle, stage)
        destination = catalog/entry['id']
        bundle.seek(0)
        with (stage/'release.zip').open('wb') as archive:
            shutil.copyfileobj(bundle, archive)
        try:
            stage.rename(destination)
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            present = json.loads((destination/'entry.json').read_text())
            if present['targets'] != entry['targets']:
                raise ValueError(f"{entry['name']} already exists with different build files. Package the build with a new version.") from exc
            return {'release': present, 'added': False}
        return {'release': entry, 'added': True}
