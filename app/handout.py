"""Signed Buddy publication for a planned Ghost. Only its envelope goes to USB."""
import re
import secrets
import struct
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from .protocol import CALLSIGNS, PHRASES, digest, load, private, public, sign, verify

DOMAIN = b'WEAZL-CODEBOOK-PUBLICATION-V2\0'

def validate_names(names):
    if any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,16}', n) for n in names):
        raise ValueError('Callsigns need 1–16 letters, numbers, underscores or hyphens')
    if len({n.lower() for n in names}) != len(names):
        raise ValueError('Choose unique callsigns')

def validate_phrases(phrases):
    if phrases is None:
        return
    if not isinstance(phrases,list) or len(phrases)!=12 or any(
        not isinstance(p,str) or not p.strip() or not re.fullmatch(r'[ -~]{1,84}',p) for p in phrases
    ):
        raise ValueError('The Buddy handout needs 12 printable phrases of 1–84 characters')

def uses_handout(plan):
    return bool(plan.get('phrases') or any(m['callsign'] not in CALLSIGNS for m in plan['members']))

def publication(plan, member):
    members=sorted(plan['members'],key=lambda m:int(m['id']))
    team=bytes.fromhex(plan['id'])
    namespace=digest(b'WEAZL HANDOUT V2\0'+team)[:16]
    content=bytearray(b'WZLCBK02'+team+namespace+struct.pack('<IB',1,13))
    for i,text in enumerate([*(plan.get('phrases') or PHRASES),'ACK'],1):
        urgency=(i+1)//2 if i<=6 else (i-5)//2 if i<=12 else 1
        replies=[5+2*urgency,6+2*urgency,13] if i<=6 else []
        content+=struct.pack('<HBBB',i,urgency,len(text),len(replies))+text.encode('ascii')
        for reply in replies:
            content+=struct.pack('<H',reply)
    content+=struct.pack('<HB',13,len(members))
    for m in members:
        name=m['callsign'].encode('ascii')
        content+=struct.pack('<QB',int(m['id']),len(name))+name
    group=team[:8]
    manifest=b'WZLCBP01'+group+team+namespace+struct.pack('<II',1,1)+digest(content)+struct.pack('<I',len(content))
    signature=sign(load(bytes.fromhex(plan['root_secret'])),DOMAIN+manifest)
    key=secrets.token_bytes(32)
    nonce=secrets.token_bytes(12)
    inner=manifest+bytes([len(signature)])+signature+key+nonce+AESGCM(key).encrypt(nonce,bytes(content),DOMAIN+manifest)
    ephemeral=private()
    own=bytes.fromhex(member['public'])
    shared=ephemeral.exchange(ec.ECDH(),ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),own))
    wrap=HKDF(hashes.SHA256(),32,b'WZL-CB-DELIVERY-V2',own+group).derive(shared)
    nonce=secrets.token_bytes(12)
    envelope=public(ephemeral)+nonce+AESGCM(wrap).encrypt(nonce,inner,own)
    peers=b''.join(struct.pack('<Q',int(m['id'])) for m in members if m['product']=='ghost' and m['id']!=member['id'])
    return {'manifest':manifest.hex(),'envelope':envelope.hex(),'peers':peers.ljust(32,b'\0').hex()}

def apply_handout(usb, package, member, certificate, nonce):
    manifest=bytes.fromhex(package['manifest'])
    if usb.exchange('codebook status','CODEBOOK ')!='CODEBOOK ACTIVE '+manifest.hex():
        image=bytes.fromhex(package['envelope'])
        usb.exchange('codebook begin '+str(len(image)),'CODEBOOK STAGING')
        for at in range(0,len(image),96):
            part=image[at:at+96]
            if usb.exchange(f'codebook chunk {at} '+part.hex(),'CODEBOOK CHUNK ')!=f'CODEBOOK CHUNK {at+len(part)}':
                raise ValueError('Handout chunk offset differs')
        usb.exchange('codebook commit','CODEBOOK INSTALLED')
    peers=package['peers']
    if usb.exchange('codebook peers '+peers,'CODEBOOK PEERS ')!='CODEBOOK PEERS '+peers:
        raise ValueError('Saved Buddy recipients differ')
    parts=usb.exchange('codebook attest '+nonce.hex(),'CODEBOOK PROOF ').split()
    if len(parts)!=4 or parts[2]!=manifest.hex():
        raise ValueError('Saved handout differs from team plan')
    proof={'manifest':parts[2],'signature':parts[3]}
    verify_handout(member,certificate,manifest.hex(),nonce,proof)
    return proof

def verify_handout(member,certificate,manifest_hex,nonce,proof):
    if len(nonce)!=32 or proof.get('manifest')!=manifest_hex:
        raise ValueError('Missing current signed handout receipt')
    cert=bytes.fromhex(certificate)
    evidence=b'WZL-CB-PROOF-V2\0'+nonce+bytes.fromhex(manifest_hex)+cert[16:24]+bytes(12)
    try:
        verify(bytes.fromhex(member['public']),bytes.fromhex(proof['signature']),evidence)
    except (KeyError,InvalidSignature) as e:
        raise ValueError('Handout receipt signature differs') from e
