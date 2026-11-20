"""Immutable complete source kit with a strict allowlist and hash manifest.
Does not include data, captures, deployment keys, traces or private credentials.
"""
from pathlib import Path
import argparse,hashlib,json,re,zipfile,os,tempfile,shutil
BASE=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('version');p.add_argument('--release-tag',help='Immutable source/tooling revision; runtime version and source validation remain exact');a=p.parse_args()
if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*',a.version):raise SystemExit('Invalid version')
release_tag=a.release_tag or a.version
if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*',release_tag):raise SystemExit('Invalid release tag')
out=BASE/'dist/weazlops'/release_tag
if out.exists():raise SystemExit('Immutable release already exists; choose a new version')
stamp=json.loads((BASE/'app/build_info.json').read_text())
actual={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest()for folder in ('app','web')for p in sorted((BASE/folder).rglob('*'))if p.is_file()and '__pycache__'not in p.parts and p.name!='build_info.json'}
if stamp.get('version')!=a.version or stamp.get('files')!=actual:raise SystemExit('Missing/stale deployed-source stamp; rebuild before packaging')
files=[]
for folder in ('app','web','tools','tests','backend'):
 for path in sorted((BASE/folder).rglob('*')):
  if not path.is_file()or '__pycache__'in path.parts:continue
  if path.is_symlink()or not path.resolve().is_relative_to(BASE):raise SystemExit('Source link escapes package')
  if path.suffix in ('.pyc','.pem','.key','.bin','.gds','.sqlite','.zip'):raise SystemExit('Unexpected private/binary source')
  files.append(path)
for name in ('Dockerfile','.dockerignore','compose.yaml','pytest.ini','requirements.txt','requirements-adapter.txt','requirements-dev.txt','requirements-lock.txt','OPERATOR-GUIDE.txt','PROTOCOL.txt','REUSE.txt','README.md'):
 path=BASE/name
 if not path.is_file():raise SystemExit('Incomplete source allowlist: '+name)
 files.append(path)
for path in files:
 body=path.read_bytes()
 if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----',body):raise SystemExit('Private key marker in '+str(path.relative_to(BASE)))
# Include licensing separately without importing unrelated parent application code.
license_files=[BASE/'LICENSE',BASE/'THIRD_PARTY_NOTICES.md',BASE/'LICENSING.md']
if any(not f.is_file()for f in license_files):raise SystemExit('License provenance missing')
records={str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest()for f in files}
if 'backend/releases.py' not in records:raise SystemExit('Firmware release validator missing')
for f in license_files:records['licenses/'+f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
source=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.package-',dir=out.parent))
try:
 with zipfile.ZipFile(stage/'corresponding-source.zip','w',zipfile.ZIP_DEFLATED)as z:
  for f in files:z.write(f,str(f.relative_to(BASE)))
  for f in license_files:z.write(f,'licenses/'+f.name)
 manifest={'product':'weazlops','version':a.version,'release_tag':release_tag,'source_sha256':source,'runtime_source_sha256':stamp['source_sha256'],'files':records,'transport':'native-usb;chrome-usb-deferred','service_port':5005,'devices_per_team':5,'source_zip_sha256':hashlib.sha256((stage/'corresponding-source.zip').read_bytes()).hexdigest()}
 (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');os.rename(stage,out)
except Exception:shutil.rmtree(stage,ignore_errors=True);raise
print(str(out))
