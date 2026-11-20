"""Exact firmware provisioning v1 codecs; no host admission signer."""
import hashlib,struct
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

ROSTER_DOMAIN=b'WZL TEAM ROSTER V1\0'
RECEIPT_DOMAIN=b'WZL TEAM INSTALLED V1\0'
ROOT_DOMAIN=b'WZL TEAM ROOT V1\0'
def check_signature(pub,message,signature):
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),pub).verify(signature,message,ec.ECDSA(hashes.SHA256()))
def directory_payload(root,lead,epoch,config,members,transaction,name='WEAZL GIG'):
    if len(root)!=65 or len(config)!=32 or len(transaction)!=16 or not 1<=len(members)<=5:raise ValueError('Invalid directory dimensions')
    b=b'WZLTP001'+hashlib.sha256(ROOT_DOMAIN+root).digest()[:16]+struct.pack('<IIQQQI',1,1,int(lead),0,epoch,1)+config+transaction+root+name.encode('ascii','replace')[:23].ljust(24,b'\0')+bytes([len(members)])
    for m in sorted(members,key=lambda m:int(m['id'])):
        b+=struct.pack('<Q',int(m['id']))+m['key']+struct.pack('<BBIBQ',m['product'],m['chip'],m['capabilities'],m['callsign'],m['incarnation'])
    b+=bytes(88*(5-len(members)))
    if len(b)!=638:raise ValueError('Invalid directory layout')
    return b
def verify_directory(wire,root,expected_members):
    if len(wire)!=711 or wire[:8]not in (b'WZLTP001',b'WZLTP002') or wire[108:173]!=root or wire[8:24]!=hashlib.sha256(ROOT_DOMAIN+root).digest()[:16]:raise ValueError('Directory root/layout mismatch')
    n=wire[638]
    if not 8<=n<=72 or any(wire[639+n:]):raise ValueError('Directory signature encoding')
    check_signature(root,(b'WZL TEAM ROSTER V2\0'if wire[:8]==b'WZLTP002'else ROSTER_DOMAIN)+wire[:638],wire[639:639+n])
    count=wire[197]
    if count!=len(expected_members) or not 1<=count<=5:raise ValueError('Directory membership count')
    generation,revision,lead,backup,epoch,config_revision=struct.unpack_from('<IIQQQI',wire,24)
    name=wire[173:197]
    if not generation or not revision or not epoch or not config_revision or not any(wire[60:92]) or not any(wire[92:108]) or not name[0] or b'\0' not in name or any(c<32 or c>126 for c in name.split(b'\0')[0]) or any(name[len(name.split(b'\0')[0]):]):raise ValueError('Directory metadata invalid')
    ids=[];keys=[];callsigns=[];leaders=set()
    for i in range(count):
        row=wire[198+88*i:286+88*i];member=struct.unpack_from('<Q',row)[0];key=row[8:73];product,chip,caps,call,inc=struct.unpack_from('<BBIBQ',row,73)
        if not member or not inc or key[0]!=4 or key==root or chip not in ((0,)if wire[:8]==b'WZLTP002'else(1,2)) or call>=7 or caps&~31 or not caps&8:raise ValueError('Directory member invalid')
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),key)
        if product==1:
            if caps&3!=3 or caps&4:raise ValueError('Ghost capabilities invalid')
        elif product==2:
            if caps!=12:raise ValueError('Drop capabilities invalid')
        else:raise ValueError('Unknown product')
        ids.append(member);keys.append(key);callsigns.append(call)
        if caps&16:leaders.add(member)
    if ids!=sorted(set(ids)) or len(set(keys))!=count or len(set(callsigns))!=count or lead not in leaders or lead==backup or (backup and backup not in leaders) or leaders-{lead,backup} or any(wire[198+88*count:638]):raise ValueError('Directory ordering/authority invalid')
    found={str(struct.unpack_from('<Q',wire,198+88*i)[0]):wire[206+88*i:271+88*i] for i in range(count)}
    if found!=expected_members:raise ValueError('Directory member binding')
    # Installed-state identity is the canonical payload hash. The signature
    # preimage above separately includes its domain separator (native crypto.hpp).
    return hashlib.sha256(wire[:638]).digest()
def verify_receipt(payload,signature,pub,wire,member,challenge):
    digest=hashlib.sha256(wire[:638]).digest()
    expected=b'WZLTI001'+wire[8:32]+digest+wire[56:108]+challenge+struct.pack('<Q',int(member))+b'\1'
    if len(payload)!=157 or payload!=expected:raise ValueError('Installed receipt context mismatch')
    check_signature(pub,RECEIPT_DOMAIN+payload,signature)
def recipient_message(group,der):return b'WZL-RECIPIENT-V1\0'+struct.pack('<Q',int(group))+der
