"""Private encrypted persistence. SQLite stores encrypted objects, public IDs only."""
from pathlib import Path
import contextlib,hashlib,hmac,json,os,re,secrets,sqlite3,threading,time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def password_hash(s):
 if not isinstance(s,str)or not 12<=len(s)<=256:raise ValueError('Password length')
 salt=secrets.token_bytes(16);return (salt+hashlib.scrypt(s.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)).hex()
def password_ok(s,encoded):
 if not isinstance(s,str)or len(s)>256:return False
 b=bytes.fromhex(encoded);return hmac.compare_digest(b[16:],hashlib.scrypt(s.encode(),salt=b[:16],n=16384,r=8,p=1,dklen=32))
class Store:
 def __init__(self,path,keypath):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();kp=Path(keypath)
  if not kp.is_file():raise ValueError('Private wrapping key missing')
  self.crypto=AESGCM(kp.read_bytes())
  with self.connection()as c:
   c.execute('pragma journal_mode=WAL');c.execute('create table if not exists objects(kind text,id text,version integer,data blob,primary key(kind,id))')
 def connection(self):
  return contextlib.closing(sqlite3.connect(self.path,timeout=30))
 def unpack(self,kind,id,b):return json.loads(self.crypto.decrypt(b[:12],b[12:],(kind+'\0'+id).encode()))
 def pack(self,kind,id,obj):
  n=secrets.token_bytes(12);return n+self.crypto.encrypt(n,json.dumps(obj,separators=(',',':')).encode(),(kind+'\0'+id).encode())
 def get(self,kind,id):
  with self.lock,self.connection()as c:
   row=c.execute('select data from objects where kind=? and id=?',(kind,id)).fetchone()
   return self.unpack(kind,id,row[0])if row else None
 def all(self,kind):
  with self.lock,self.connection()as c:return [self.unpack(kind,id,b)for id,b in c.execute('select id,data from objects where kind=?',(kind,))]
 def put(self,kind,id,obj):
  with self.lock,self.connection()as c:
   c.execute('insert into objects values(?,?,1,?) on conflict(kind,id) do update set data=excluded.data,version=version+1',(kind,id,self.pack(kind,id,obj)));c.commit()
 def put_many(self,items):
  with self.lock,self.connection()as c:
   c.execute('begin immediate')
   for kind,id,obj in items:c.execute('insert into objects values(?,?,1,?) on conflict(kind,id) do update set data=excluded.data,version=version+1',(kind,id,self.pack(kind,id,obj)))
   c.commit()
 def commit_assignments(self,plan,bindings):
  """Commit team, current fleet ownership and superseded rows atomically.

  Only fresh verified devices belong in bindings. Historical offline receipts
  remain evidence of an earlier installation, not a current fleet observation.
  """
  with self.lock:
   now=time.time();items=[('team',plan['id'],plan)]
   for old in self.all('team'):
    if old['id']==plan['id']:continue
    changed=False
    for member in old['members']:
     if member.get('binding')and member['binding']['mac']in bindings and member['status']=='ready':
      member.update(status='reissued',reissued_at=now);changed=True
    if changed:items.append(('team',old['id'],old))
   for member in plan['members']:
    binding=member.get('binding')
    if binding and binding['mac']in bindings:
     items.append(('device',binding['mac'],{'mac':binding['mac'],'team':plan['id'],'member':member['id'],'verified_at':now}))
   self.put_many(items)
 def modify(self,kind,id,callback):
  with self.lock,self.connection()as c:
   c.execute('begin immediate');row=c.execute('select data from objects where kind=? and id=?',(kind,id)).fetchone()
   if not row:raise ValueError('Object missing')
   obj=self.unpack(kind,id,row[0]);callback(obj);c.execute('update objects set data=?,version=version+1 where kind=? and id=?',(self.pack(kind,id,obj),kind,id));c.commit();return obj
 def accounts(self):
  with self.lock,self.connection() as c:
   rows=c.execute("select id,data from objects where kind='account' order by id collate nocase")
   return [{'username':name,'role':self.unpack('account',name,data).get('role','operator')} for name,data in rows]
 def create_account(self,username,password,role='operator',*,bootstrap=False):
  if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}',username):
   raise ValueError('Use 1–48 letters, numbers, dots, underscores or hyphens. Start with a letter or number.')
  if role not in ('admin','operator'):raise ValueError('Choose Operator or Administrator.')
  if not isinstance(password,str) or not 12<=len(password)<=256:raise ValueError('Use a password of 12–256 characters.')
  data=self.pack('account',username,{'password':password_hash(password),'role':role})
  with self.lock,self.connection() as c:
   c.execute('begin immediate')
   if bootstrap and c.execute("select 1 from objects where kind='account' limit 1").fetchone():return
   if c.execute("select 1 from objects where kind='account' and id=? collate nocase",(username,)).fetchone():
    raise FileExistsError('That username already exists.')
   c.execute("insert into objects values('account',?,1,?)",(username,data));c.commit()
  return {'username':username,'role':role}
 def login(self,username,password):
  if not isinstance(username,str):return None
  with self.connection() as c:
   row=c.execute("select id,data from objects where kind='account' and id=? collate nocase",(username,)).fetchone()
  if not row or not password_ok(password,self.unpack('account',*row)['password']):return None
  token=secrets.token_urlsafe(32);self.put('session',hashlib.sha256(token.encode()).hexdigest(),{'username':row[0],'csrf':secrets.token_urlsafe(24),'expires':time.time()+28800});return token
 def session(self,token):
  row=self.get('session',hashlib.sha256((token or '').encode()).hexdigest());return row if row and row['expires']>time.time()else None
