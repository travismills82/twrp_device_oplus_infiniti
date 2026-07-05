# TWRP curl / SFTP prebuilt

This recovery includes a tested ARM64 Android curl binary with:

- FTP
- FTPS through OpenSSL
- SCP and SFTP through libssh2
- CA certificate bundle
- SSH `known_hosts` support

Runtime files:

```text
/system/bin/curl
/system/bin/twrp-curl
/system/bin/twrp-sftp
/system/etc/security/cacerts/cacert.pem
```

Temporary credentials should be staged only under:

```text
/tmp/twrp-network/known_hosts
/tmp/twrp-network/id_rsa
/tmp/twrp-network/id_rsa.pub
```

Example:

```sh
mkdir -p /tmp/twrp-network
chmod 0700 /tmp/twrp-network

twrp-sftp download \
  travis@192.168.3.10:/home/travis/twrp-sftp-test/download.txt \
  /tmp/download.txt

twrp-sftp upload \
  /tmp/recovery.log \
  travis@192.168.3.10:/home/travis/recovery.log
```

The binary should report `libssh2` and list `ftp`, `ftps`, `scp`, and `sftp` in `curl --version`.
