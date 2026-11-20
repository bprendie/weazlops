"""Private local deployment preparation. No secret output or baked-in bench fleet."""
from pathlib import Path
import argparse,json,os,secrets,shutil,re
p=argparse.ArgumentParser();p.add_argument('--credentials',type=Path);p.add_argument('--bench-allowlist',type=Path);args=p.parse_args()
os.umask(0o077)
base=Path(__file__).resolve().parents[1];private=base/'.runtime/private';private.mkdir(parents=True,exist_ok=True);(base/'.runtime/data').mkdir(parents=True,exist_ok=True)
bootstrap=args.credentials or Path(os.environ.get('WZL_BOOTSTRAP_CREDENTIALS',str(base/'.private/admin-bootstrap.json')))
if not(private/'admin-bootstrap.json').exists():
 if not bootstrap.is_file():raise SystemExit('Supply a private JSON credentials file with --credentials PATH')
 data=json.loads(bootstrap.read_text())
 if not isinstance(data.get('username'),str)or not 1<=len(data['username'])<=64 or not isinstance(data.get('password'),str)or not 12<=len(data['password'])<=256:raise SystemExit('Invalid private bootstrap credentials')
 (private/'admin-bootstrap.json').write_text(json.dumps(data))
for name,data in [('master.key',secrets.token_bytes(32)),('worker.token',secrets.token_urlsafe(48).encode())]:
 path=private/name
 if not path.exists():path.write_bytes(data)
 os.chmod(path,0o600)
os.chmod(private/'admin-bootstrap.json',0o600)
if args.bench_allowlist:
 values=json.loads(args.bench_allowlist.read_text())
 if not isinstance(values,list)or any(not isinstance(v,str)or not re.fullmatch('[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}',v)for v in values):raise SystemExit('Invalid explicit bench allowlist')
 (private/'bench-allowlist.json').write_text(json.dumps([v.upper()for v in values]));os.chmod(private/'bench-allowlist.json',0o600)
print('Private deployment material prepared. Existing keys and device guard are retained.')
