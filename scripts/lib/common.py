"""
HOOK shared library — validation, rate limiting, logging, caching, safe execution.
Imported by all enrichment scripts via: exec(open('scripts/lib/common.py').read())

This file is designed to be exec()'d into the caller's namespace, not imported,
because the enrichment scripts run inline Python inside bash.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# --- Paths (container-ready: all configurable via env vars) ---------------

# script_dir is set by the calling script before exec()'ing this file
_caller_script_dir = locals().get('script_dir', os.getcwd())
HOOK_DIR = os.environ.get('HOOK_DIR', os.path.dirname(_caller_script_dir))
HOOK_DATA_DIR = os.environ.get('HOOK_DATA_DIR', os.path.join(HOOK_DIR, 'data'))
LOG_DIR = os.environ.get('HOOK_LOG_DIR', os.path.expanduser('~/.openclaw/logs/hook'))
LOG_ENABLED = os.environ.get('HOOK_LOG_ENABLED', '1') == '1'
CACHE_DIR = os.environ.get('HOOK_CACHE_DIR', os.path.join(HOOK_DATA_DIR, 'cache'))

# --- Logging --------------------------------------------------------------

def _ensure_log_dir():
    if LOG_ENABLED:
        os.makedirs(LOG_DIR, exist_ok=True)

def log(level, script, message, data=None):
    """Structured JSON logging to file."""
    if not LOG_ENABLED:
        return
    _ensure_log_dir()
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': level,
        'script': script,
        'message': message
    }
    if data:
        entry['data'] = data
    try:
        log_file = os.path.join(LOG_DIR, f'enrichment-{datetime.now(timezone.utc).strftime("%Y-%m-%d")}.jsonl')
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass  # Logging should never crash the script

def log_info(script, message, data=None):
    log('INFO', script, message, data)

def log_warn(script, message, data=None):
    log('WARN', script, message, data)

def log_error(script, message, data=None):
    log('ERROR', script, message, data)

# --- Input Validation -----------------------------------------------------

_IP_RE = re.compile(r'^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$')
_DOMAIN_RE = re.compile(r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')
_HASH_RE = re.compile(r'^[a-fA-F0-9]{32,64}$')

def validate_ip(ip):
    """Validate IPv4 address. Returns sanitized string or raises ValueError."""
    ip = str(ip).strip()
    if not _IP_RE.match(ip):
        raise ValueError(f'Invalid IP address: {repr(ip[:80])}')
    return ip

def validate_domain(domain):
    """Validate domain name. Returns sanitized string or raises ValueError."""
    domain = str(domain).strip().lower().rstrip('.')
    if len(domain) > 253:
        raise ValueError(f'Domain too long: {len(domain)} chars')
    if not _DOMAIN_RE.match(domain):
        raise ValueError(f'Invalid domain: {repr(domain[:80])}')
    return domain

def validate_hash(file_hash):
    """Validate file hash (MD5/SHA1/SHA256). Returns sanitized string or raises ValueError."""
    file_hash = str(file_hash).strip().lower()
    if not _HASH_RE.match(file_hash):
        raise ValueError(f'Invalid hash: {repr(file_hash[:80])}')
    if len(file_hash) not in (32, 40, 64):
        raise ValueError(f'Hash length {len(file_hash)} not valid (expected 32/40/64)')
    return file_hash

# --- IOC Cache ------------------------------------------------------------

# TTLs in hours — configurable via env vars
CACHE_TTL = {
    'ip':     int(os.environ.get('HOOK_CACHE_TTL_IP', '24')),
    'domain': int(os.environ.get('HOOK_CACHE_TTL_DOMAIN', '72')),
    'hash':   int(os.environ.get('HOOK_CACHE_TTL_HASH', '168')),
}

def _cache_key(ioc_type, ioc_value):
    """Generate a safe filename from IOC type and value."""
    # Replace filesystem-unsafe chars
    safe = re.sub(r'[^a-zA-Z0-9._\-]', '_', ioc_value)
    return os.path.join(CACHE_DIR, ioc_type, safe + '.json')

def cache_get(ioc_type, ioc_value):
    """Check cache for a fresh enrichment result.
    Returns (result_dict, True) if cached and fresh, (None, False) if stale/missing."""
    path = _cache_key(ioc_type, ioc_value)
    try:
        with open(path, 'r') as f:
            entry = json.load(f)
        cached_at = datetime.fromisoformat(entry['cached_at'])
        ttl_hours = entry.get('ttl_hours', CACHE_TTL.get(ioc_type, 24))
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        if age_hours < ttl_hours:
            result = entry['result']
            result['_cache'] = {
                'hit': True,
                'cached_at': entry['cached_at'],
                'age_hours': round(age_hours, 1),
                'ttl_hours': ttl_hours
            }
            log_info('cache', f'Cache hit for {ioc_type}:{ioc_value}', {
                'age_hours': round(age_hours, 1),
                'ttl_hours': ttl_hours
            })
            return result, True
        else:
            log_info('cache', f'Cache stale for {ioc_type}:{ioc_value}', {
                'age_hours': round(age_hours, 1),
                'ttl_hours': ttl_hours
            })
            return None, False
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None, False

def cache_put(ioc_type, ioc_value, result):
    """Store an enrichment result in cache."""
    path = _cache_key(ioc_type, ioc_value)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {
        'cached_at': datetime.now(timezone.utc).isoformat(),
        'ttl_hours': CACHE_TTL.get(ioc_type, 24),
        'ioc_type': ioc_type,
        'ioc_value': ioc_value,
        'result': result
    }
    try:
        with open(path, 'w') as f:
            json.dump(entry, f, indent=2)
        log_info('cache', f'Cached result for {ioc_type}:{ioc_value}')
    except Exception as e:
        log_warn('cache', f'Failed to cache {ioc_type}:{ioc_value}: {e}')

def cache_lookup(ioc_value):
    """Auto-detect IOC type and look up in cache. Returns (result, hit, ioc_type)."""
    if _IP_RE.match(ioc_value):
        result, hit = cache_get('ip', ioc_value)
        return result, hit, 'ip'
    elif _HASH_RE.match(ioc_value) and len(ioc_value) in (32, 40, 64):
        result, hit = cache_get('hash', ioc_value)
        return result, hit, 'hash'
    elif _DOMAIN_RE.match(ioc_value):
        result, hit = cache_get('domain', ioc_value)
        return result, hit, 'domain'
    return None, False, 'unknown'

def cache_stats():
    """Return cache statistics."""
    stats = {'total': 0, 'by_type': {}, 'fresh': 0, 'stale': 0}
    now = datetime.now(timezone.utc)
    for ioc_type in ['ip', 'domain', 'hash']:
        type_dir = os.path.join(CACHE_DIR, ioc_type)
        count = 0
        fresh = 0
        stale = 0
        if os.path.isdir(type_dir):
            for fname in os.listdir(type_dir):
                if not fname.endswith('.json'):
                    continue
                count += 1
                try:
                    with open(os.path.join(type_dir, fname), 'r') as f:
                        entry = json.load(f)
                    cached_at = datetime.fromisoformat(entry['cached_at'])
                    ttl = entry.get('ttl_hours', CACHE_TTL.get(ioc_type, 24))
                    age = (now - cached_at).total_seconds() / 3600
                    if age < ttl:
                        fresh += 1
                    else:
                        stale += 1
                except Exception:
                    stale += 1
        stats['by_type'][ioc_type] = {'total': count, 'fresh': fresh, 'stale': stale}
        stats['total'] += count
        stats['fresh'] += fresh
        stats['stale'] += stale
    stats['cache_dir'] = CACHE_DIR
    return stats

def cache_clear(ioc_type=None, stale_only=False):
    """Clear cache entries. Returns count of files removed."""
    removed = 0
    now = datetime.now(timezone.utc)
    types = [ioc_type] if ioc_type else ['ip', 'domain', 'hash']
    for t in types:
        type_dir = os.path.join(CACHE_DIR, t)
        if not os.path.isdir(type_dir):
            continue
        for fname in os.listdir(type_dir):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(type_dir, fname)
            if stale_only:
                try:
                    with open(fpath, 'r') as f:
                        entry = json.load(f)
                    cached_at = datetime.fromisoformat(entry['cached_at'])
                    ttl = entry.get('ttl_hours', CACHE_TTL.get(t, 24))
                    if (now - cached_at).total_seconds() / 3600 < ttl:
                        continue  # Still fresh, skip
                except Exception:
                    pass  # Can't read it, remove it
            os.remove(fpath)
            removed += 1
    return removed

# --- Rate Limiting --------------------------------------------------------

RATE_LIMIT_DIR = os.path.join(LOG_DIR, '.ratelimit')

# Limits per API (requests per minute)
API_RATE_LIMITS = {
    'virustotal': int(os.environ.get('HOOK_VT_RATE_LIMIT', '4')),
    'abuseipdb': int(os.environ.get('HOOK_ABUSE_RATE_LIMIT', '15')),
    'censys': int(os.environ.get('HOOK_CENSYS_RATE_LIMIT', '4')),
}

def rate_limit_wait(api_name):
    """Block until we're within rate limits for the given API.
    Uses file-based timestamps so limits apply across concurrent scripts."""
    limit = API_RATE_LIMITS.get(api_name)
    if not limit:
        return

    os.makedirs(RATE_LIMIT_DIR, exist_ok=True)
    lock_file = os.path.join(RATE_LIMIT_DIR, f'{api_name}.timestamps')

    max_wait = 120  # Never wait more than 2 minutes
    start = time.time()

    while time.time() - start < max_wait:
        now = time.time()
        window_start = now - 60  # 1-minute sliding window

        # Read existing timestamps
        timestamps = []
        try:
            with open(lock_file, 'r') as f:
                for line in f:
                    ts = float(line.strip())
                    if ts > window_start:
                        timestamps.append(ts)
        except FileNotFoundError:
            pass

        if len(timestamps) < limit:
            # Under limit — record this request and proceed
            timestamps.append(now)
            with open(lock_file, 'w') as f:
                for ts in timestamps:
                    f.write(f'{ts}\n')
            return

        # Over limit — wait until oldest timestamp exits the window
        oldest = min(timestamps)
        wait_time = (oldest + 60) - now + 0.5  # +0.5s buffer
        if wait_time > 0:
            log_info(api_name, f'Rate limit reached, waiting {wait_time:.1f}s')
            time.sleep(min(wait_time, 15))  # Check again every 15s max

    log_warn(api_name, 'Rate limit wait exceeded 120s, proceeding anyway')

# --- Safe Execution -------------------------------------------------------

def curl_json(args, api_name=None, timeout=15):
    """Execute curl and parse JSON response. Rate-limited if api_name provided."""
    if api_name:
        rate_limit_wait(api_name)

    try:
        r = subprocess.run(
            ['curl', '-s', '--max-time', str(timeout)] + args,
            capture_output=True, text=True, timeout=timeout + 5
        )
        if r.returncode != 0:
            log_warn(api_name or 'curl', f'curl returned {r.returncode}', {'stderr': r.stderr[:200]})
            return {'error': f'curl_exit_{r.returncode}'}
        if not r.stdout.strip():
            return {'error': 'empty_response'}
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        log_error(api_name or 'curl', f'JSON parse error: {e}')
        return {'error': 'invalid_json'}
    except subprocess.TimeoutExpired:
        log_warn(api_name or 'curl', f'Request timed out after {timeout}s')
        return {'error': 'timeout'}
    except Exception as e:
        log_error(api_name or 'curl', f'Unexpected error: {e}')
        return {'error': str(e)[:200]}

def run_cmd(cmd, timeout=5):
    """Execute a command and return stdout. Returns empty string on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            log_warn('cmd', f'{cmd[0]} returned {r.returncode}', {'stderr': r.stderr[:200]})
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        log_warn('cmd', f'{cmd[0]} timed out after {timeout}s')
        return ''
    except FileNotFoundError:
        log_error('cmd', f'{cmd[0]} not found on PATH')
        return ''
    except Exception as e:
        log_error('cmd', f'{cmd[0]} error: {e}')
        return ''

# --- Output ---------------------------------------------------------------

def output_json(data):
    """Print JSON to stdout (the script's return value)."""
    print(json.dumps(data, indent=2))

def error_exit(script, message, ioc=None):
    """Print error JSON and exit."""
    result = {'error': message}
    if ioc:
        result['ioc'] = ioc
    log_error(script, message)
    output_json(result)
    sys.exit(1)
