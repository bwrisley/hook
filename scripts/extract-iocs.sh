#!/bin/bash
# extract-iocs.sh — Extract IOCs from text input
# Usage: echo "alert text" | ./scripts/extract-iocs.sh
# Output: JSON object with extracted IOCs by type

python3 <<'PYEOF'
import re, json, sys, ipaddress

MAX_INPUT_BYTES = 1_000_000  # 1MB max input

text = sys.stdin.read(MAX_INPUT_BYTES + 1)
if len(text) > MAX_INPUT_BYTES:
    print(json.dumps({'error': f'Input exceeds {MAX_INPUT_BYTES} byte limit'}))
    sys.exit(1)

# IPv4
ips = list(set(re.findall(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b', text)))
# Filter private/reserved IPs properly
def is_public_ip(ip_str):
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_global
    except ValueError:
        return False
ips = [ip for ip in ips if is_public_ip(ip)]

# Domains (defanged and normal)
cleaned = text.replace('hxxp', 'http').replace('[.]', '.').replace('(.)', '.')
domains = list(set(re.findall(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(?:com|net|org|io|co|info|biz|xyz|top|ru|cn|tk|ml|ga|cf|gq|cc|pw|club|online|site|tech|shop|work|live|pro|me|us|uk|de|fr|br|in|jp|kr|au|ca|nl|se|ch|it|es|pl|cz|at|be)\b', cleaned)))

# Filter common FP domains
fp_domains = {
    'microsoft.com', 'google.com', 'windows.com', 'office.com', 'windowsupdate.com',
    'digicert.com', 'verisign.com', 'symantec.com', 'akamai.com', 'cloudflare.com',
    'amazonaws.com', 'azure.com', 'outlook.com', 'live.com', 'office365.com',
    'microsoftonline.com', 'gstatic.com', 'googleapis.com', 'apple.com',
    'icloud.com', 'github.com', 'githubusercontent.com'
}
domains = [d for d in domains if d.lower() not in fp_domains]

# SHA256
sha256 = list(set(re.findall(r'\b[a-fA-F0-9]{64}\b', text)))

# SHA1
sha1 = list(set(re.findall(r'\b[a-fA-F0-9]{40}\b', text)))
sha1 = [h for h in sha1 if not any(h.lower() in s.lower() for s in sha256)]

# MD5
md5 = list(set(re.findall(r'\b[a-fA-F0-9]{32}\b', text)))
md5 = [h for h in md5 if not any(h.lower() in s.lower() for s in sha256 + sha1)]

result = {
    'iocs': {
        'ips': sorted(ips),
        'domains': sorted(domains),
        'sha256': sha256,
        'sha1': sha1,
        'md5': md5
    },
    'counts': {
        'ips': len(ips),
        'domains': len(domains),
        'hashes': len(sha256) + len(sha1) + len(md5),
        'total': len(ips) + len(domains) + len(sha256) + len(sha1) + len(md5)
    }
}

print(json.dumps(result, indent=2))
PYEOF
