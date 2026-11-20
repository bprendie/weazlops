"""Verify committed configuration proofs, never a transport's success boolean."""
import struct
from .protocol import verify,digest,CONFIG

def verify_receipt(plan,member,payload,sig,nonce):
 if len(payload)!=157 or payload[:8]!=b'WZLTI001':raise ValueError('Invalid receipt')
 expected=b'WZLTI001'+bytes.fromhex(plan['id'])+struct.pack('<II',1,1)+digest(bytes.fromhex(plan['roster'])[:638])+struct.pack('<I',1)+CONFIG+bytes.fromhex(plan['operation'])+nonce+struct.pack('<Q',int(member['id']))+b'\1'
 if payload!=expected:raise ValueError('Receipt does not match current transaction/challenge')
 verify(bytes.fromhex(member['public']),sig,b'WZL TEAM INSTALLED V1\0'+payload)
def verify_owner(plan,member,der,sig,nonce):
 if der!=bytes.fromhex(plan['recipient']):raise ValueError('Recording owner differs')
 verify(bytes.fromhex(member['public']),sig,b'WZL-RECIPIENT-V1\0'+bytes.fromhex(plan['certificate'])[8:16]+der+nonce)
def verify_binding(member,binding,image,payload,sig,nonce):
 expected=b'WZLPP002'+digest(image[:-73])+nonce+bytes.fromhex(binding['mac'].replace(':',''))+bytes([1 if binding['chip']=='esp32s3'else 2,{'original':1,'xl':2,'headless':3}[binding['profile']]])+struct.pack('<Q',int(member['id']))+b'\2'
 if payload!=expected:raise ValueError('Hardware/package proof differs')
 verify(bytes.fromhex(member['public']),sig,b'WZL ONE VISIT INSTALLED V2\0'+payload)
