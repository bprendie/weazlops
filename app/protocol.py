"""Planned team identities and canonical v2 package. No USB/backend dependencies."""
import hashlib,secrets,struct
from cryptography.hazmat.primitives.asymmetric import ec,rsa
from cryptography.hazmat.primitives import hashes,serialization

CALLSIGNS=['STONEY','CRAWL','LINK','BETTY','NUGGET','gh05t-we4zR','gh05t-BLOCK']
PHRASES=['CHILLIN BUDDY','CRUISIN THE GIG','GIG IS TAXED','ALL IS NOT CHILL','ATZ NO CARRIER','MAYDAY! ZERO CHILL!','STAY CRUSTY BUD','MELLOW HASH ACK','OMW BUUUUDDY','SENDING JUICE','OMW BARE-METAL!','NUKING THE GIG']
CONFIG=hashlib.sha256(b''.join(p.encode()+b'\0' for p in PHRASES)).digest()
def digest(b):return hashlib.sha256(b).digest()
def private():return ec.generate_private_key(ec.SECP256R1())
def scalar(k):return k.private_numbers().private_value.to_bytes(32,'big')
def load(b):return ec.derive_private_key(int.from_bytes(b,'big'),ec.SECP256R1())
def public(k):return k.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
def sign(k,b):return k.sign(b,ec.ECDSA(hashes.SHA256()))
def verify(k,s,b):ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),k).verify(s,b,ec.ECDSA(hashes.SHA256()))
def padded(s):
 if not 8<=len(s)<=72:raise ValueError('ECDSA length')
 return bytes([len(s)])+s+bytes(72-len(s))
def signature(b):
 if len(b)!=73 or not 8<=b[0]<=72 or any(b[1+b[0]:]):raise ValueError('ECDSA canonical padding')
 return b[1:1+b[0]]
def new_plan(name,slots,phrases=None):
 from .handout import validate_names,validate_phrases
 validate_phrases(phrases)
 if not isinstance(name,str) or not 1<=len(name.encode('ascii'))<=23 or any(ord(c)<32 or ord(c)>126 for c in name):raise ValueError('Team name needs1..23 ASCII characters')
 if not 1<=len(slots)<=5:raise ValueError('A team has1..5 members')
 names=[s['callsign'] for s in slots]
 validate_names(names)
 # The signed v2 directory retains its stable numeric role labels for older Drops.
 spare=iter(n for n in CALLSIGNS if n not in names)
 directory_names={n:n if n in CALLSIGNS else next(spare) for n in names}
 if sum(bool(s.get('lead')) for s in slots)!=1:raise ValueError('Choose one Ghost lead')
 for s in slots:
  if s['product'] not in ('ghost','drop') or (s.get('lead') and s['product']!='ghost') or s.get('profile','any') not in ('any','original','xl','headless'):raise ValueError('Invalid member role/profile')
  if s['product']=='drop'and s.get('profile','any')not in ('any','headless')or s['product']=='ghost'and s.get('profile','any')=='headless':raise ValueError('Product/display mismatch')
 root=private();members=[]
 for s in slots:
  key=private();members.append({**s,'id':str(secrets.randbits(63) or 1),'secret':scalar(key).hex(),'public':public(key).hex(),'incarnation':secrets.randbits(63) or 1,'status':'waiting','binding':None})
 rootpub=public(root);team=digest(b'WZL TEAM ROOT V1\0'+rootpub)[:16];lead=int(next(m['id']for m in members if m.get('lead')));operation=secrets.token_bytes(16)
 cert=bytearray(384);cert[:8]=b'WZLROST2';struct.pack_into('<QQQ',cert,8,int.from_bytes(team[:8],'little'),lead,1);cert[32:35]=bytes([len(members),1,1])
 ordered=sorted(members,key=lambda m:int(m['id']))
 for i,m in enumerate(ordered):struct.pack_into('<Q',cert,40+40*i,int(m['id']));cert[48+40*i:80+40*i]=digest(bytes.fromhex(m['public']))
 cert[240:305]=rootpub;sig=sign(root,bytes(cert[:305]));cert[305:378]=padded(sig)
 payload=b'WZLTP002'+team+struct.pack('<IIQQQI',1,1,lead,0,1,1)+CONFIG+operation+rootpub+name.encode().ljust(24,b'\0')+bytes([len(members)])
 for m in ordered:
  ghost=m['product']=='ghost';payload+=struct.pack('<Q',int(m['id']))+bytes.fromhex(m['public'])+struct.pack('<BBIBQ',1 if ghost else 2,0,(27 if m.get('lead') else 11)if ghost else 12,CALLSIGNS.index(directory_names[m['callsign']]),m['incarnation'])
 payload+=bytes(88*(5-len(members)));assert len(payload)==638
 roster=payload+padded(sign(root,b'WZL TEAM ROSTER V2\0'+payload))
 owner=rsa.generate_private_key(public_exponent=65537,key_size=3072)
 der=owner.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
 ownersig=padded(sign(root,b'WZL-RECIPIENT-V1\0'+struct.pack('<Q',int.from_bytes(team[:8],'little'))+der))
 return {**({'phrases':phrases} if phrases else {}),'id':team.hex(),'name':name,'operation':operation.hex(),'root_secret':scalar(root).hex(),'root_public':rootpub.hex(),'members':members,'certificate':bytes(cert).hex(),'roster':roster.hex(),'recipient':der.hex(),'recipient_signature':ownersig.hex(),'recovery_private':owner.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode(),'origin':'app','state':'preparing'}
def package(plan,member,mac,chip,profile):
 if chip not in ('esp32s3','esp32c5') or profile not in ('original','xl','headless'):raise ValueError('Hardware binding required')
 physical=bytes.fromhex(mac.replace(':',''));assert len(physical)==6
 der=bytes.fromhex(plan['recipient'])
 body=b'WZLPK002'+bytes.fromhex(plan['operation'])+physical+bytes([1 if chip=='esp32s3' else 2,{'original':1,'xl':2,'headless':3}[profile]])+struct.pack('<Q',int(member['id']))+bytes.fromhex(member['secret'])+bytes.fromhex(plan['certificate'])+bytes.fromhex(plan['roster'])+struct.pack('<H',len(der))+der+bytes.fromhex(plan['recipient_signature'])
 return body+padded(sign(load(bytes.fromhex(plan['root_secret'])),b'WZL ONE VISIT PACKAGE V2\0'+digest(body)))

def public_plan(plan):
 return {k:v for k,v in plan.items() if k in ('id','name','operation','origin','state','journey','created','phrases')}|{'members':[{k:v for k,v in m.items()if k not in ('secret',)}for m in plan['members']]}

def import_offline(blob,known_recipients=()):
 """Validate lead escrow for trusted import; never certify unknown hardware facts."""
 from .evidence.setup_wire import verify_directory
 from .evidence.trust import roster as verify_certificate
 if not isinstance(blob,bytes)or not 1503<=len(blob)<=4096 or blob[:8]not in (b'WZLOFF02',b'WZLOFF03',b'WZLOFF04'):raise ValueError('Unsupported offline custody envelope')
 v3=blob[:8]in (b'WZLOFF03',b'WZLOFF04')
 root=load(blob[8:40]);rootpub=public(root);cert=blob[200:584];wire=blob[584:1295];pn,sn=struct.unpack_from('<HH',blob,1295)
 if not 91<=pn<=512 or sn>2048 or len(blob)!=1299+pn+sn+40+(73 if v3 else 0):raise ValueError('Offline custody lengths invalid')
 if wire[:8]!=b'WZLTP002'or wire[108:173]!=rootpub or cert[240:305]!=rootpub:raise ValueError('Offline root mismatch')
 certinfo=verify_certificate(cert);count=wire[197]
 if cert[32]!=count:raise ValueError('Offline certificate count differs')
 slots=struct.unpack_from('<QQQQQ',blob,len(blob)-40);members=[];keys={};rows={}
 for i in range(count):
  at=198+88*i;id=str(struct.unpack_from('<Q',wire,at)[0]);pub=wire[at+8:at+73];product,chip,caps,call,inc=struct.unpack_from('<BBIBQ',wire,at+73);keys[id]=pub;rows[id]=(product,call,inc)
 verify_directory(wire,rootpub,keys)
 if {id:digest(pub).hex()for id,pub in keys.items()}!=certinfo['members']:raise ValueError('Offline authority identities differ')
 if any(blob[40+32*count:200])or any(slots[count:])or len(set(slots[:count]))!=count or str(slots[0])!=certinfo['approver_member_id']:raise ValueError('Offline slot layout invalid')
 for i,number in enumerate(slots[:count]):
  id=str(number)
  if id not in keys:raise ValueError('Offline slot has no membership')
  secret=blob[40+32*i:72+32*i];key=load(secret)
  if public(key)!=keys[id]:raise ValueError('Offline member custody key mismatch')
  product,call,inc=rows[id];members.append({'id':id,'secret':secret.hex(),'public':keys[id].hex(),'product':'ghost'if product==1 else'drop','profile':'any'if product==1 else'headless','callsign':CALLSIGNS[call],'lead':i==0,'incarnation':inc,'status':'waiting','binding':None})
 der=blob[1299:1299+pn]
 pubkey=serialization.load_der_public_key(der)
 if not((isinstance(pubkey,rsa.RSAPublicKey)and pubkey.key_size==3072)or (blob[:8]==b'WZLOFF04'and isinstance(pubkey,ec.EllipticCurvePublicKey)and isinstance(pubkey.curve,ec.SECP256R1))):raise ValueError('Unsupported offline recovery key')
 if sn:
  owner=serialization.load_der_private_key(blob[1299+pn:1299+pn+sn],None)
  if not isinstance(owner,(rsa.RSAPrivateKey,ec.EllipticCurvePrivateKey))or owner.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)!=der:raise ValueError('Offline recovery custody differs from recipient')
  pem=owner.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
 else:
  pem=next((p['recovery_private']for p in known_recipients if p['recipient']==der.hex()),None)
  if not pem:raise ValueError('Offline team uses another organizer; this app has no recovery key')
 group=struct.unpack_from('<Q',cert,8)[0];name=wire[173:197].split(b'\0')[0].decode('ascii');team=wire[8:24].hex()
 ownersig=blob[1299+pn+sn:1299+pn+sn+73]if v3 else padded(sign(root,b'WZL-RECIPIENT-V1\0'+struct.pack('<Q',group)+der))
 verify(rootpub,signature(ownersig),b'WZL-RECIPIENT-V1\0'+struct.pack('<Q',group)+der)
 return {'id':team,'name':name,'operation':wire[92:108].hex(),'root_secret':scalar(root).hex(),'root_public':rootpub.hex(),'members':members,'certificate':cert.hex(),'roster':wire.hex(),'recipient':der.hex(),'recipient_signature':ownersig.hex(),'recovery_private':pem,'origin':'offline-lead','state':'imported','custody':'app','escrow_digest':digest(blob).hex()}
