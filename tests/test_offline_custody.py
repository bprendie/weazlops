import struct,pytest
from app.protocol import *

def escrow(plan):
 keys=b''.join(bytes.fromhex(m['secret'])for m in plan['members']).ljust(160,b'\0');owner=serialization.load_pem_private_key(plan['recovery_private'].encode(),None);priv=owner.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption());der=bytes.fromhex(plan['recipient']);ids=b''.join(struct.pack('<Q',int(m['id']))for m in plan['members']).ljust(40,b'\0')
 return b'WZLOFF03'+bytes.fromhex(plan['root_secret'])+keys+bytes.fromhex(plan['certificate'])+bytes.fromhex(plan['roster'])+struct.pack('<HH',len(der),len(priv))+der+priv+bytes.fromhex(plan['recipient_signature'])+ids

def test_same_authority_import_and_member_recovery_custody():
 p=new_plan('Offline',[{'product':'ghost','callsign':'STONEY','lead':True},{'product':'ghost','callsign':'BETTY'},{'product':'drop','callsign':'gh05t-we4zR'}]);b=escrow(p);q=import_offline(b)
 for key in ('id','operation','root_public','root_secret','roster','certificate','recipient','recovery_private'):assert p[key]==q[key]
 assert [m['public']for m in q['members']]==[m['public']for m in p['members']];assert q['origin']=='offline-lead'
 for at in (0,9,50,200,400,600,1296,len(b)-1):
  bad=bytearray(b);bad[at]^=1
  with pytest.raises(Exception):import_offline(bytes(bad))
 with pytest.raises(ValueError):import_offline(b[:-1])
 assert 'root_secret'not in public_plan(q)


def test_p256_offline_recovery_same_authority_and_curve_boundary():
 p=new_plan('Fresh offline',[{'product':'ghost','callsign':'STONEY','lead':True},{'product':'drop','callsign':'gh05t-we4zR'}])
 owner=ec.generate_private_key(ec.SECP256R1())
 der=owner.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
 p['recipient']=der.hex();p['recovery_private']=owner.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
 p['recipient_signature']=padded(sign(load(bytes.fromhex(p['root_secret'])),b'WZL-RECIPIENT-V1\0'+struct.pack('<Q',int.from_bytes(bytes.fromhex(p['id'])[:8],'little'))+der)).hex()
 blob=b'WZLOFF04'+escrow(p)[8:];q=import_offline(blob)
 assert q['id']==p['id']and q['recipient']==p['recipient']and q['recovery_private']==p['recovery_private']
 with pytest.raises(ValueError):import_offline(b'WZLOFF03'+blob[8:])
 for at in (1295,1297,1299,1400,len(blob)-1):
  bad=bytearray(blob);bad[at]^=1
  with pytest.raises(Exception):import_offline(bytes(bad))
