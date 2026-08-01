import os
import sys
import zipfile
import subprocess
import tempfile
import struct
import hashlib

def encode_varint(n):
    res = bytearray()
    while n >= 0x80:
        res.append((n & 0x7f) | 0x80)
        n >>= 7
    res.append(n & 0x7f)
    return bytes(res)

def encode_bytes_field(field_num, data):
    tag = (field_num << 3) | 2
    return encode_varint(tag) + encode_varint(len(data)) + data

def make_crx(extension_dir, output_crx, output_zip, pem_key_path=None):
    os.makedirs(os.path.dirname(output_crx), exist_ok=True)
    
    # 1. Create ZIP package
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(extension_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, extension_dir)
                zf.write(abs_path, rel_path)
                
    with open(output_zip, 'rb') as f:
        zip_data = f.read()

    # 2. Key management for CRX3 signing
    temp_key = False
    if not pem_key_path or not os.path.exists(pem_key_path):
        temp_key = True
        pem_key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        pem_key_path = pem_key_file.name
        pem_key_file.close()
        subprocess.run(["openssl", "genrsa", "-out", pem_key_path, "2048"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    try:
        # Export public key in DER format
        pub_der = subprocess.check_output(["openssl", "rsa", "-in", pem_key_path, "-pubout", "-outform", "DER"], stderr=subprocess.DEVNULL)

        # Compute crx_id (first 16 bytes of SHA256 of public key)
        sha256_pub = hashlib.sha256(pub_der).digest()
        crx_id = sha256_pub[:16]

        # Construct signed_header_data
        signed_header_data = encode_bytes_field(1, crx_id)

        # Construct data to sign according to CRX3 specification
        prefix = b"CRX3 SignedData\x00"
        signed_header_len = struct.pack("<I", len(signed_header_data))
        to_sign = prefix + signed_header_len + signed_header_data + zip_data

        # Sign data with RSA-SHA256
        with tempfile.NamedTemporaryFile(delete=False) as tf_in:
            tf_in.write(to_sign)
            tf_in_path = tf_in.name

        sig_out_path = tempfile.mktemp(suffix=".sig")
        subprocess.run([
            "openssl", "dgst", "-sha256", "-sign", pem_key_path, "-out", sig_out_path, tf_in_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(sig_out_path, "rb") as f:
            signature = f.read()

        if os.path.exists(tf_in_path): os.remove(tf_in_path)
        if os.path.exists(sig_out_path): os.remove(sig_out_path)

        # Construct AsymmetricKeyProof
        proof = encode_bytes_field(1, pub_der) + encode_bytes_field(2, signature)

        # Construct CrxFileHeader
        header = encode_bytes_field(2, proof) + encode_bytes_field(10000, signed_header_data)

        # Construct full CRX3 binary
        magic = b"Cr24"
        version = struct.pack("<I", 3)
        header_len = struct.pack("<I", len(header))

        crx_bytes = magic + version + header_len + header + zip_data

        with open(output_crx, "wb") as f:
            f.write(crx_bytes)

        print(f"ZIP package created: {output_zip} ({len(zip_data)} bytes)")
        print(f"CRX3 binary created: {output_crx} ({len(crx_bytes)} bytes)")

    finally:
        if temp_key and os.path.exists(pem_key_path):
            os.remove(pem_key_path)

if __name__ == "__main__":
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ext_dir = os.path.join(repo_root, "extension")
    out_crx = os.path.join(repo_root, "dist", "bengal-download-manager-extension.crx")
    out_zip = os.path.join(repo_root, "dist", "bengal-download-manager-extension.zip")
    make_crx(ext_dir, out_crx, out_zip)
