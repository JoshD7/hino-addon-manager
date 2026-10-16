"""Optional, user-approved application updater; separate from WoW addon updates."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

APP_VERSION = '4.2.1'
REPOSITORY = 'JoshD7/hino-addon-manager'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
SETUP_NAME = 'HinoAddonManager-Setup.exe'
HASH_NAME = SETUP_NAME + '.sha256'
MAX_INSTALLER_BYTES = 160 * 1024 * 1024

def parsed_version(value):
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value).strip())
    return tuple(map(int, m.groups())) if m else None

def select_update(release, current=APP_VERSION):
    """Only accept newer tagged releases with both exact named assets."""
    version = parsed_version(release.get('tag_name', ''))
    installed = parsed_version(current)
    if not version or not installed or version <= installed or release.get('draft') or release.get('prerelease'):
        return None
    assets = {a.get('name'): a for a in release.get('assets', []) if isinstance(a, dict)}
    setup, digest = assets.get(SETUP_NAME), assets.get(HASH_NAME)
    if not setup or not digest:
        return None
    for asset in (setup, digest):
        u = asset.get('browser_download_url', '')
        if not u.startswith(f'https://github.com/{REPOSITORY}/releases/download/'):
            return None
    return {'version': '.'.join(map(str, version)), 'setup': setup['browser_download_url'], 'digest': digest['browser_download_url']}

def _read_https(url, cap):
    if urlsplit(url).scheme != 'https':
        raise ValueError('Only HTTPS update URLs are accepted')
    req = Request(url, headers={'User-Agent': 'HinoAddonManager/' + APP_VERSION, 'Accept': 'application/vnd.github+json'})
    with urlopen(req, timeout=20) as response:
        if urlsplit(response.geturl()).scheme != 'https':
            raise ValueError('HTTPS downgrade detected')
        data = response.read(cap + 1)
        if len(data) > cap:
            raise ValueError('Update response exceeded size limit')
    return data

def check_latest():
    return select_update(json.loads(_read_https(API_URL, 2 * 1024 * 1024).decode('utf-8')))

def parse_checksum(content):
    text = content.decode('ascii').strip()
    m = re.fullmatch(r'([0-9a-fA-F]{64})(?:\s+\*?' + re.escape(SETUP_NAME) + r')?', text)
    if not m:
        raise ValueError('Invalid setup SHA256 checksum file')
    return m.group(1).lower()

def stage_installer(update):
    expected = parse_checksum(_read_https(update['digest'], 2048))
    content = _read_https(update['setup'], MAX_INSTALLER_BYTES)
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError('Installer SHA256 does not match the release checksum')
    folder = Path(tempfile.mkdtemp(prefix='hino-app-update-'))
    path = folder / SETUP_NAME
    path.write_bytes(content)
    return path

def helper_path():
    """Independent PowerShell helper installed alongside the application EXE."""
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return root / 'HinoUpdateHelper.ps1'

def run_installer(installer, expected_version):
    """Hand off to a separate process that waits for Hino to exit."""
    if sys.platform != 'win32':
        raise OSError('Self-updates require Windows')
    if not parsed_version(expected_version):
        raise ValueError('Invalid target version')
    script = helper_path()
    if not script.is_file():
        raise FileNotFoundError('Update helper is missing; install V4.0.2 once manually.')
    exe = Path(sys.executable).resolve()
    log_dir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'HinoAddonManager' / 'UpdateLogs'
    return subprocess.Popen([
        'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-WindowStyle', 'Hidden', '-File', str(script),
        '-Installer', str(Path(installer).resolve()), '-ParentPid', str(os.getpid()),
        '-ExpectedVersion', expected_version, '-InstallDir', str(exe.parent),
        '-LogDir', str(log_dir)
    ], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
