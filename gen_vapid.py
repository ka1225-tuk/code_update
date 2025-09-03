# gen_vapid.py  — VAPID 키 직접 생성 (P-256)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64

def b64url(b: bytes) -> str:
    # base64url(= -, _) + 패딩 제거
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

# 1) 개인키 생성 (secp256r1 = P-256)
priv = ec.generate_private_key(ec.SECP256R1())

# 2) PRIVATE: 32바이트 big-endian 정수
priv_int = priv.private_numbers().private_value
priv_bytes = priv_int.to_bytes(32, "big")

# 3) PUBLIC: uncompressed(0x04 || X || Y), 총 65바이트
pub = priv.public_key().public_numbers()
x = pub.x.to_bytes(32, "big")
y = pub.y.to_bytes(32, "big")
pub_bytes = b"\x04" + x + y

print("PUBLIC =", b64url(pub_bytes))
print("PRIVATE =", b64url(priv_bytes))
