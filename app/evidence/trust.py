"""Verify existing designated-approver WZLROST2 and signed RECON capabilities.
No signing key is generated or imported by the server. Initial root binding is an
explicit administrator TOFU operation, distinct from signature verification.
"""
import hashlib,struct
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

def public(value):
    if len(value)!=65 or value[0]!=4:raise ValueError('P256 uncompressed key required')
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),value)
def roster(cert,pinned_root=None,minimum_epoch=0):
    if len(cert)!=384 or cert[:8]!=b'WZLROST2':raise ValueError('Invalid roster size or domain')
    group,approver,epoch=struct.unpack_from('<QQQ',cert,8);count=cert[32]
    if not group or not approver or not epoch or not 1<=count<=5 or cert[33]!=1 or cert[34]!=1 or any(cert[35:40]):raise ValueError('Invalid finalized roster schema')
    root=cert[240:305]
    if pinned_root is not None and root!=pinned_root:raise ValueError('Designated approver root changed')
    if epoch<minimum_epoch:raise ValueError('Roster rollback rejected')
    n=cert[305]
    if not 8<=n<=72 or any(cert[306+n:]):raise ValueError('Invalid roster signature encoding')
    public(root).verify(cert[306:306+n],cert[:305],ec.ECDSA(hashes.SHA256()))
    members={}
    for i in range(5):
        row=cert[40+i*40:80+i*40];member=struct.unpack_from('<Q',row)[0]
        if i>=count:
            if any(row):raise ValueError('Unused roster member not zero')
        else:
            if not member or str(member) in members or row[8:].hex() in members.values():raise ValueError('Duplicate or invalid roster member')
            members[str(member)]=row[8:].hex()
    if str(approver) not in members:raise ValueError('Approver missing from roster')
    return {'group_id':str(group),'approver_member_id':str(approver),'epoch':epoch,'members':members,'root_public_key_hex':root.hex(),'root_fingerprint':hashlib.sha256(root).hexdigest()}
def capability(blob,cert,member,pub,role):
    info=roster(cert);member=int(member)
    if len(blob)!=144 or blob[:4]!=b'RCAP' or blob[4]!=1 or blob[5]!=role or role not in (1,2) or any(blob[6:8]):raise ValueError('Invalid signed capability schema')
    group,subject,epoch=struct.unpack_from('<QQQ',blob,8);digest=hashlib.sha256(pub).digest()
    if str(group)!=info['group_id'] or subject!=member or not 0<epoch<=info['epoch'] or blob[32:64]!=digest or info['members'].get(str(member))!=digest.hex():raise ValueError('Capability membership, public key or epoch mismatch')
    public(pub);n=blob[64]
    if not 8<=n<=72 or any(blob[65+n:]):raise ValueError('Invalid capability signature encoding')
    public(bytes.fromhex(info['root_public_key_hex'])).verify(blob[65:65+n],blob[:64],ec.ECDSA(hashes.SHA256()))
    return {'member_id':str(member),'role':'human' if role==1 else 'recorder','public_fingerprint':digest.hex(),'endorsement_epoch':epoch}
def identity_proof(challenge,member,pub,signature):
    if len(challenge)!=32:raise ValueError('Invalid challenge')
    message=bytearray(128);message[:15]=b'WEAZL-USB-ID-V2';message[16:48]=challenge;struct.pack_into('<Q',message,48,int(member));message[56:121]=pub
    if len(message)!=128:raise ValueError('USB identity proof preimage must be exactly128 bytes')
    public(pub).verify(signature,bytes(message),ec.ECDSA(hashes.SHA256()))
    return True
