#!/usr/bin/env python3
"""Seal a disposable release and exercise the real recovery AVB verifier."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

device=Path(__file__).resolve().parents[1]
root=Path(sys.argv[1]).resolve()
image=Path(sys.argv[2]).resolve()
tools=device/"tools/op15_update_release.py"
decoder=root/"external/jsoncpp"
avb=root/"external/avb/libavb"
with tempfile.TemporaryDirectory(prefix="op15-signed-release-qa-") as temp:
    d=Path(temp)
    key=d/"ephemeral.pem"
    subprocess.run(["openssl","genpkey","-algorithm","ED25519","-out",str(key)],check=True)
    key.chmod(0o600)
    pub=subprocess.check_output(["openssl","pkey","-in",str(key),"-pubout","-outform","DER"])[-32:].hex()
    identity,profiles,notes=d/"identity.json",d/"profiles.json",d/"notes"
    subprocess.run([sys.executable,str(tools),"identity","--build","2001","--channel","stable",
                    "--public-key",pub,"--output",str(identity)],check=True)
    hashes={name:"d"*64 for name in ("boot","init_boot","vendor_boot","dtbo","vbmeta","from_recovery")}
    profiles.write_text(json.dumps([dict(hashes,project="24863",slot="_b")]))
    notes.write_text("Disposable signing test; never publish.")
    cmd=[sys.executable,str(tools),"sign","--identity",str(identity),"--image",str(image),
         "--profiles",str(profiles),"--notes",str(notes),"--key",str(key),"--output",str(d),"--tag","fixture-2001"]
    subprocess.run(cmd,check=True)
    # Refuse a key mismatch and an unsigned flavor. Neither may replace the sealed fixture.
    identity_json=json.loads(identity.read_text())
    identity.write_text(json.dumps(dict(identity_json,public_key="0"*64)))
    assert subprocess.run(cmd,capture_output=True).returncode != 0
    identity.write_text(json.dumps(dict(identity_json,channel="development")))
    assert subprocess.run(cmd,capture_output=True).returncode != 0
    native=d/"check"
    objects=[]
    for c in sorted(avb.glob("*.c")) + sorted((avb/"sha").glob("*.c")):
        obj=d/(c.stem+".o")
        subprocess.run([os.environ.get("CC","gcc"),"-std=gnu11","-DAVB_COMPILATION","-I"+str(avb/"sha"),
                        "-c",str(c),"-o",str(obj)],check=True)
        objects.append(str(obj))
    subprocess.run([os.environ.get("CXX","g++"),"-std=c++17","-Wall","-Wextra","-Werror",
                    "-Wno-ignored-attributes","-I"+str(decoder/"include"),
                    "-I"+str(root/"system/libbase/include"),"-I"+str(root/"external/avb"),
                    str(device/"scripts/test-active-slot-updater-image.cpp"),
                    *[str(decoder/f"src/lib_json/json_{x}.cpp") for x in ("reader","value","writer")],
                    *objects,"-lcrypto","-o",str(native)],check=True)
    subprocess.run([str(native),str(image),str(d/"corrupt.img"),str(d/"twrp-update.json"),
                    str(d/"twrp-update.json.sig"),pub],check=True)
