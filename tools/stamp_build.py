from pathlib import Path
import sys,hashlib,json,re
base=Path(__file__).resolve().parents[1];version=sys.argv[1]
if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*',version):raise SystemExit('Invalid build version')
files={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest()for folder in ('app','web')for p in sorted((base/folder).rglob('*'))if p.is_file()and '__pycache__'not in p.parts and p.name!='build_info.json'}
source=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest();(base/'app/build_info.json').write_text(json.dumps({'version':version,'source_sha256':source,'files':files},indent=2)+'\n');print(version,source)
