"""Exercise the real byte-framed transport with production UTF-8 status text."""
import pytest
from app.serial_transport import USB
class Bytes:
 def __init__(self,chunks):self.chunks=list(chunks)
 @property
 def in_waiting(self):return len(self.chunks[0])if self.chunks else 0
 def read(self,n):return self.chunks.pop(0)if self.chunks else b''
 def write(self,p):return len(p)
def unit(chunks):
 u=USB.__new__(USB);u.device=Bytes(chunks);u.pending=bytearray();return u
def test_utf8_status_survives_fragmented_codepoint_and_retains_next_line():
 text='PLANNED ready=3 READY — HAND OUT\n'.encode()
 at=text.index(b'\xe2')
 u=unit([text[:at+1],text[at+1:at+2],text[at+2:]+b'PLAN COMPLETE\n'])
 assert u.exchange('planned status','PLANNED ')=='PLANNED ready=3 READY — HAND OUT'
 assert u.exchange('plan status','PLAN ')=='PLAN COMPLETE'
def test_invalid_utf8_and_oversize_are_rejected_without_replacement():
 with pytest.raises(UnicodeDecodeError):unit([b'PLANNED \xff\n']).exchange('planned status','PLANNED ')
 with pytest.raises(ValueError,match='exceeds bound'):unit([b'x'*4097]).exchange('planned status','PLANNED ')
