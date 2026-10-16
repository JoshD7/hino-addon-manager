"""Hino Addon Manager - Windows Tkinter GUI, standard library only."""
import json, os, re, shutil, tempfile, threading, urllib.request, urllib.error, zipfile, time, ssl, sys, socket, webbrowser, html
from pathlib import Path
import tkinter as tk
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    TkinterDnD = None
    DND_FILES = None
from tkinter import ttk, filedialog, messagebox, simpledialog

APP='Hino Addon Manager'
import hino_selfupdate as selfupdate
CONFIG=Path.home()/'.hino-addon-manager.json'
HISTORY=Path.home()/'.hino-addon-manager-history.json'
UA={'User-Agent':'HinoAddonManager/3.5.0','Accept':'application/vnd.github+json'}
MAX_ZIP=650*1024*1024
RARE_SOURCE='CurseForge/RareScanner-Forever'
SOURCE_REGISTRY=Path.home()/'.hino-addon-manager-sources.json'
RARE_URL='https://www.curseforge.com/wow/addons/rarescanner/files/all?gameVersionTypeId=88568&page=1&pageSize=20'

def load_config():
    try: return json.loads(CONFIG.read_text(encoding='utf-8'))
    except Exception: return {'wow':'D:/World of Warcraft/_classic_beta_','sources':{},'installed_tags':{}}
def save_config(c): CONFIG.write_text(json.dumps(c,indent=2),encoding='utf-8')
def read_history():
    try:
        data=json.loads(HISTORY.read_text(encoding='utf-8'))
        return data if isinstance(data,list) else []
    except (OSError,ValueError,TypeError):
        return []

def write_history(event, addons='', detail=''):
    from datetime import datetime
    records=read_history()
    records.insert(0,{'date':datetime.now().strftime('%Y-%m-%d %H:%M'),
                      'event':str(event)[:80], 'addons':str(addons)[:160], 'detail':str(detail)[:300]})
    HISTORY.write_text(json.dumps(records[:250],indent=2),encoding='utf-8')

def load_source_registry():
    """Persistent project identities; never infer a download URL from a title."""
    try:
        value=json.loads(SOURCE_REGISTRY.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError,TypeError):return {}

def save_source_registry(registry):
    if not isinstance(registry,dict):raise ValueError('Invalid source registry')
    temp=SOURCE_REGISTRY.with_suffix('.json.tmp')
    temp.write_text(json.dumps(registry,indent=2,sort_keys=True),encoding='utf-8')
    temp.replace(SOURCE_REGISTRY)

def identify_source(item, registry=None):
    """Return source evidence without treating a project ID as download permission."""
    registry=registry if registry is not None else load_source_registry()
    name=item['name']
    saved=registry.get(name,{})
    if isinstance(saved,dict) and saved.get('provider') and saved.get('project_id'):
        return {'provider':saved['provider'],'project_id':str(saved['project_id']),
                'evidence':'saved source association','download_authorized':False}
    project=item.get('curse_project_id')
    if project and re.fullmatch(r'\d{1,12}',str(project)):
        return {'provider':'curseforge','project_id':str(project),
                'evidence':'TOC X-Curse-Project-ID','download_authorized':False}
    repo=source_from_metadata(item)
    if repo:return {'provider':'github','project_id':repo,
                    'evidence':'TOC repository URL','download_authorized':False}
    if item.get('wago_id'):return {'provider':'wago','project_id':item['wago_id'],
        'evidence':'TOC X-Wago-ID; online provider not integrated','download_authorized':False}
    if item.get('wowi_id'):return {'provider':'wowinterface','project_id':item['wowi_id'],
        'evidence':'TOC X-WoWI-ID; online provider not integrated','download_authorized':False}
    return {'provider':'unknown','project_id':None,'evidence':'no reliable project identifier',
            'download_authorized':False}

def record_source(item, registry=None):
    """Save verified metadata without overwriting an explicit previous association."""
    registry=registry if registry is not None else load_source_registry()
    match=identify_source(item,{})
    if match['provider']=='unknown':return False
    name=item['name']
    if name in registry:return False
    registry[name]={'provider':match['provider'],'project_id':match['project_id'],
                    'evidence':match['evidence']}
    save_source_registry(registry)
    return True

def addon_group(item):
    """Return stable package key; don't merge unrelated projects by title alone."""
    name=item['name'] if isinstance(item,dict) else str(item)
    if name in ('Questie','QuestieDB'):return 'Questie + QuestieDB'
    if name in ('Bagnon','BagBrother') or name.startswith('Bagnon_'):return 'Bagnon family'
    if name=='GearQuestForever' or name.startswith('GearQuestForever_'):return 'GearQuest Forever'
    if name=='Polestar' or name.startswith('Polestar_') or name in ('PolestarCodex','PolestarGuides','PolestarItemData','PolestarQuestDatabase'):return 'Polestar Guides'
    return name

POLESTAR_CURSEFORGE_ID='1744437'  # Confirmed from the user's authenticated CurseForge search.

def declared_provider(item, registry=None):
    """Only use verified TOC source identity or an explicitly identified Polestar family."""
    if addon_group(item)=='Polestar Guides':
        return {'provider':'curseforge','project_id':POLESTAR_CURSEFORGE_ID,
                'evidence':'Polestar addon family; CurseForge project confirmed by API search',
                'download_authorized':False}
    return identify_source(item,registry)

def simple_status(status):
    if status=='Update available':return 'Update available'
    if status=='Up to date':return 'Up to date'
    if status=='No compatible release':return 'No Forever release'
    if status=='Version unverified':return 'Version unverified'
    if status in ('Check failed','Unable to verify version','Compatibility unverified','Not checked / unverified','Review release assets','Review installed version'):
        return 'Check required'
    if status=='Installed newer':return 'Installed newer'
    return 'Check required'

def package_groups(items):
    """Stable, ordered mapping of packages to their actual installed folders."""
    groups={}
    for item in items:groups.setdefault(addon_group(item),[]).append(item)
    return groups

def status_category(status):
    if status=='Update available':return 'Updates available'
    if status=='Up to date':return 'Verified up to date'
    if status in ('Check failed','Unable to verify version','Version unverified','No compatible release'):return 'Unable to verify'
    return 'Not checked'

def package_status(statuses):
    """Never claim a package is current when any component is unverified."""
    if any(s=='Update available' for s in statuses):return 'Update available'
    if statuses and all(s=='Up to date' for s in statuses):return 'Up to date'
    if any(s=='Check failed' for s in statuses):return 'Check failed'
    if statuses and all(s=='No compatible release' for s in statuses):return 'No compatible release'
    if statuses and all(s=='Version unverified' for s in statuses):return 'Version unverified'
    if any(status_category(s)=='Unable to verify' for s in statuses):return 'Unable to verify'
    return 'Not checked / unverified'

def interface_summary(raw):
    versions=list(dict.fromkeys(re.findall(r'\b\d{5,6}\b',str(raw or ''))))
    if not versions:return 'Unknown'
    return versions[0]+(f' (+{len(versions)-1})' if len(versions)>1 else '')

def toc_info(folder):
    tocs=list(folder.glob('*.toc'))
    if not tocs:return None
    data={'name':folder.name,'version':'Unknown','title':folder.name,'interface':'','source':'','source_candidates':[],'curse_project_id':'','part_of':'','dependencies':[],'wowi_id':'','wago_id':'','toc_files':[]}
    for toc in tocs:
        data['toc_files'].append(toc.name)
        try:
            for line in toc.read_text(encoding='utf-8-sig',errors='replace').splitlines():
                m=re.match(r'^##\s*(Title|Version|Interface|X-Website|X-Repository|X-GitHub|X-Source|X-Project-URL|X-Curse-Project-ID|X-Part-Of|Dependencies|RequiredDeps|X-WoWI-ID|X-Wago-ID)\s*:\s*(.*)',line,re.I)
                if m:
                    k,v=m.group(1).lower(),m.group(2).strip()
                    if k=='title':data['title']=re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',v)
                    elif k=='version':data['version']=v
                    elif k=='interface':data['interface']=v
                    elif k=='x-curse-project-id' and re.fullmatch(r'\d{1,12}',v):data['curse_project_id']=v
                    elif k=='x-part-of':data['part_of']=v
                    elif k in ('dependencies','requireddeps'):data['dependencies'].extend(x.strip() for x in v.split(',') if x.strip())
                    elif k=='x-wowi-id':data['wowi_id']=v
                    elif k=='x-wago-id':data['wago_id']=v
                    elif k in ('x-website','x-repository','x-github','x-source','x-project-url'):
                        data['source_candidates'].append(v)
                        if not data['source']:data['source']=v
        except OSError:pass
    return data

def resolve_wow(path):
    p=Path(path).expanduser()
    if p.name.lower()=='addons' and p.parent.name.lower()=='interface': return p.parent.parent
    if (p/'Interface'/'AddOns').is_dir():return p
    for sub in ('_classic_beta_','_retail_','_classic_','_classic_era_','_ptr_'):
        if (p/sub/'Interface'/'AddOns').is_dir():return p/sub
    if p.is_dir():
        matches=[q.parent.parent for q in p.glob('*/Interface/AddOns') if q.is_dir()]
        if len(matches)==1:return matches[0]
    return p

def scan(path):
    root=resolve_wow(path)/'Interface'/'AddOns' 
    if not root.is_dir():raise FileNotFoundError(f'AddOns folder not found:\n{root}')
    items=[i for f in sorted(root.iterdir(),key=lambda p:p.name.lower()) if f.is_dir() for i in [toc_info(f)] if i]
    # Only inherit source IDs when a module explicitly names a parent, or a known package relationship is present.
    parents={i['name']:i for i in items if i.get('curse_project_id')}
    for item in items:
        if item.get('curse_project_id'):continue
        name=item['name']
        declared=item.get('part_of','').strip()
        parent=(declared if declared in parents else
                'GearQuestForever' if name.startswith('GearQuestForever_') else
                'Bagnon' if name.startswith('Bagnon_') else
                'Bagnon' if name=='BagBrother' else None)
        if parent in parents:
            item['curse_project_id']=parents[parent]['curse_project_id']
            item['inherited_project_id']=True
    registry=load_source_registry()
    changed=False
    for item in items:
        match=identify_source(item,registry)
        if match['provider']!='unknown' and item['name'] not in registry:
            registry[item['name']]={'provider':match['provider'],'project_id':match['project_id'],'evidence':match['evidence']}
            changed=True
        item['source_identity']=identify_source(item,registry)
    if changed:save_source_registry(registry)
    return items

def curseforge_url(item):
    project=item.get('curse_project_id','')
    return 'https://www.curseforge.com/wow/addons/'+project if re.fullmatch(r'\d{1,12}',str(project)) else ''

def source_from_metadata(item):
    """Only link explicitly declared GitHub projects, never guessed addon names."""
    candidates=item.get('source_candidates') or [item.get('source','')]
    for value in candidates:
        url=str(value).strip()
        match=re.search(r'(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)',url,re.I)
        if match:
            try:return parse_repo(match.group(1)+'/'+match.group(2))
            except ValueError:continue
    return None


def compatible_interfaces(old, new):
    """Require an actual interface intersection, not just a version number."""
    a=set(re.findall(r'\b\d{5,6}\b',old or ''))
    b=set(re.findall(r'\b\d{5,6}\b',new or ''))
    return bool(a and b and a.intersection(b))


def candidate_github_asset(item, release):
    """Conservative candidate selection: single release ZIP and newer version tag."""
    if not release or not release.get('tag'):return None
    assets=[a for a in release.get('assets',[]) if a.get('name','').lower().endswith('.zip') and a.get('browser_download_url')]
    if len(assets)!=1:return None
    local=version_tuple(item.get('version',''))
    remote=version_tuple(release.get('tag',''))
    if not local or not remote or remote<=local:return None
    return assets[0]


def parse_repo(value):
    value=value.strip().removesuffix('.git').rstrip('/')
    m=re.fullmatch(r'(?:https://github\.com/)?([\w.-]+)/([\w.-]+)',value,re.I)
    if not m:raise ValueError('Enter a GitHub repository such as owner/repo or https://github.com/owner/repo')
    return f'{m.group(1)}/{m.group(2)}'

def secure_context():
    """Verify HTTPS with the native Windows trust store where available.

    Never disable TLS verification. On older Python, use the platform SSL
    context and report actionable errors if its CA store is incomplete.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def secure_open(request, timeout=25):
    try:
        return urllib.request.urlopen(request, timeout=timeout, context=secure_context())
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, 'reason', None), ssl.SSLCertVerificationError):
            raise RuntimeError('HTTPS certificate validation failed. Run Install-Secure-Connection.bat, then restart the app. '
                               'If the problem continues, update Windows trusted certificates. SSL verification remains enabled. '
                               f'Details: {exc}') from exc
        raise

# CurseForge 3rd-party API: metadata-only discovery. Key is kept in memory, never persisted.
# Windows Credential Manager: this application's generic credential lives in the
# current Windows user's protected credential vault, never in Hino JSON config.
CF_CREDENTIAL_TARGET='HinoAddonManager/CurseForgeAPI/v1'

def _windows_credential_api():
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    class CREDENTIALW(ctypes.Structure):
        _fields_=[('Flags',wintypes.DWORD),('Type',wintypes.DWORD),('TargetName',wintypes.LPWSTR),
                  ('Comment',wintypes.LPWSTR),('LastWritten',wintypes.FILETIME),
                  ('CredentialBlobSize',wintypes.DWORD),('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),
                  ('Persist',wintypes.DWORD),('AttributeCount',wintypes.DWORD),
                  ('Attributes',ctypes.c_void_p),('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]
    dll=ctypes.WinDLL('Advapi32.dll',use_last_error=True)
    dll.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    dll.CredReadW.restype=wintypes.BOOL
    dll.CredWriteW.argtypes=[ctypes.POINTER(CREDENTIALW),wintypes.DWORD]
    dll.CredWriteW.restype=wintypes.BOOL
    dll.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
    dll.CredDeleteW.restype=wintypes.BOOL
    dll.CredFree.argtypes=[ctypes.c_void_p]
    return ctypes,wintypes,CREDENTIALW,dll

def load_cf_credential():
    api=_windows_credential_api()
    if api is None:return ''
    ctypes,wintypes,CRED,dll=api
    ptr=ctypes.POINTER(CRED)()
    if not dll.CredReadW(CF_CREDENTIAL_TARGET,1,0,ctypes.byref(ptr)):
        if ctypes.get_last_error()==1168:return ''  # ERROR_NOT_FOUND
        raise OSError(ctypes.get_last_error(),'Windows Credential Manager could not read key')
    try:
        c=ptr.contents
        blob=ctypes.string_at(c.CredentialBlob,c.CredentialBlobSize) if c.CredentialBlobSize else b''
        return blob.decode('utf-16-le')
    finally:dll.CredFree(ptr)

def save_cf_credential(key):
    api=_windows_credential_api()
    if api is None:raise RuntimeError('Secure credential saving requires Windows')
    key=key.strip()
    if not key:raise ValueError('Enter the CurseForge API key before saving')
    ctypes,wintypes,CRED,dll=api
    data=key.encode('utf-16-le')
    if len(data)>2560:raise ValueError('API key is too long')
    buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    cred=CRED();cred.Type=1;cred.TargetName=CF_CREDENTIAL_TARGET
    cred.UserName='HinoAddonManager';cred.CredentialBlobSize=len(data)
    cred.CredentialBlob=ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist=2  # CRED_PERSIST_LOCAL_MACHINE: per-user profile, survives restart
    if not dll.CredWriteW(ctypes.byref(cred),0):
        raise OSError(ctypes.get_last_error(),'Windows Credential Manager could not save key')

def delete_cf_credential():
    api=_windows_credential_api()
    if api is None:return
    ctypes,wintypes,CRED,dll=api
    if not dll.CredDeleteW(CF_CREDENTIAL_TARGET,1,0) and ctypes.get_last_error()!=1168:
        raise OSError(ctypes.get_last_error(),'Windows Credential Manager could not delete key')

CF_API='https://api.curseforge.com/v1'
CF_GAME_ID=1

def cf_request(api_key, path, params=None, opener=secure_open):
    from urllib.parse import urlencode
    if not api_key or not api_key.strip():
        raise ValueError('Enter your personal CurseForge API key in Settings.')
    if not re.fullmatch(r'/[A-Za-z0-9/_-]+',path):
        raise ValueError('Invalid CurseForge API path')
    url=CF_API+path+('?' + urlencode(params) if params else '')
    req=urllib.request.Request(url,headers={'x-api-key':api_key.strip(), 'Accept':'application/json','User-Agent':'HinoAddonManager/3.5.0'})
    try:
        with opener(req,timeout=20) as response:
            raw=response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:raise ValueError('CurseForge response exceeds size limit')
            result=json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):raise RuntimeError('CurseForge rejected the API key or permissions (HTTP '+str(exc.code)+').') from None
        if exc.code==429:raise RuntimeError('CurseForge rate limit reached; retry later.') from None
        raise RuntimeError('CurseForge request failed (HTTP '+str(exc.code)+').') from None
    if not isinstance(result,dict) or 'data' not in result:
        raise ValueError('Unexpected CurseForge API response')
    return result['data']

def cf_search(api_key, query):
    if not query.strip():raise ValueError('Enter an addon name to search.')
    data=cf_request(api_key,'/mods/search',{'gameId':CF_GAME_ID,'searchFilter':query.strip()[:100],'pageSize':30,'sortField':2,'sortOrder':'desc'})
    if not isinstance(data,list):raise ValueError('Unexpected search results')
    return [{'id':x.get('id'),'name':x.get('name','Unnamed'),'slug':x.get('slug',''),'summary':x.get('summary','')} for x in data if isinstance(x,dict) and isinstance(x.get('id'),int)]

def cf_files(api_key, project_id):
    if not re.fullmatch(r'\d{1,12}',str(project_id)):raise ValueError('Invalid CurseForge project ID')
    data=cf_request(api_key,f'/mods/{project_id}/files',{'pageSize':50})
    if not isinstance(data,list):raise ValueError('Unexpected file results')
    return [{'id':f.get('id'),'name':f.get('displayName') or f.get('fileName',''), 'versions':f.get('gameVersions') or [],'date':f.get('fileDate',''), 'releaseType':f.get('releaseType')} for f in data if isinstance(f,dict)]

def cf_forever_evidence(file):
    versions=[str(x).lower() for x in file.get('versions',[]) if isinstance(x,(str,int))]
    return any('1.60.1' in x or 'forever' in x for x in versions)

def cf_project_for(item):
    """Prefer declared source evidence; do not infer unrelated projects by title."""
    identity=declared_provider(item)
    if identity.get('provider')=='curseforge' and re.fullmatch(r'\d{1,12}',str(identity.get('project_id',''))):
        return str(identity['project_id'])
    return None


def cf_file_version(file):
    """Read a release version from the filename; ambiguous names are unverified."""
    name=str(file.get('name',''))
    matches=re.findall(r'(?<!\d)v?(\d+\.\d+(?:\.\d+)?(?:[.-](?:beta|alpha|rc)\d*)?)',name,re.I)
    # Do not mistake Forever client version 1.60.1 for the addon version.
    matches=[x for x in matches if x!='1.60.1']
    if len(set(matches))!=1:return ()
    return version_tuple(matches[0])


def cf_release_status(installed, files):
    """Evidence-based metadata comparison, never install eligibility."""
    if not files:return 'No compatible release',None
    forever=[f for f in files if cf_forever_evidence(f)]
    if not forever:return 'No compatible release',None
    local=version_tuple(installed)
    available=[(cf_file_version(f),f) for f in forever]
    available=[x for x in available if x[0]]
    if not local or not available:return 'Version unverified',None
    latest=max(available,key=lambda x:x[0])
    if latest[0]>local:return 'Update available',latest[1]
    if latest[0]==local:return 'Up to date',latest[1]
    return 'Installed newer',latest[1]

def test_github_connection():
    req=urllib.request.Request('https://api.github.com/repos/Questie/Questie/releases?per_page=1',headers=UA)
    with secure_open(req,timeout=20) as response:
        data=json.load(response)
    if not isinstance(data,list):
        raise RuntimeError('GitHub returned an unexpected response.')
    return ('GitHub API connection verified with HTTPS certificate validation. ' + ('Latest release: '+str(data[0].get('tag_name','unknown')) if data else 'No releases returned.'))

def official_rarescanner():
    """Read official Forever listing. No unofficial mirrors or unverified downloads."""
    req=urllib.request.Request(RARE_URL,headers={'User-Agent':'Mozilla/5.0 HinoAddonManager/3.5.1','Accept':'text/html'})
    try:
        with secure_open(req,timeout=20) as response:
            page=response.read(3*1024*1024).decode('utf-8','replace')
    except Exception as exc:
        return {'repo':RARE_SOURCE,'tag':'','assets':[],'page':RARE_URL,
                'notice':'Official CurseForge page unavailable; open it in your browser to check Forever releases.'}
    # Only Forever-named releases are eligible. The page may be JS-rendered;
    # failure to parse must never be treated as proof of up-to-date status.
    candidates=re.findall(r'RareScanner[_\s-]*FOREVER[_\s-]*1\.60\.1[._\s-]*b(\d+)',html.unescape(page),re.I)
    if not candidates:
        return {'repo':RARE_SOURCE,'tag':'','assets':[],'page':RARE_URL,
                'notice':'Cannot read Forever releases automatically. Open official CurseForge listing.'}
    build=max(map(int,candidates))
    return {'repo':RARE_SOURCE,'tag':f'1.60.1.b{build}','assets':[], 'page':RARE_URL,
            'notice':'Official Forever release found. Download its ZIP from CurseForge and drag it into this app.'}

def latest(repo):
    if repo==RARE_SOURCE or repo.lower()==RARE_SOURCE:
        return official_rarescanner()
    # GitHub /releases/latest may not resolve workflow-published bundle tags.
    # Read the release list, then choose the newest stable published release.
    endpoints=[f'https://api.github.com/repos/{repo}/releases/latest',
               f'https://api.github.com/repos/{repo}/releases?per_page=20']
    errors=[]
    for endpoint in endpoints:
        try:
            req=urllib.request.Request(endpoint,headers=UA)
            with secure_open(req,timeout=20) as response:
                data=json.load(response)
            releases=data if isinstance(data,list) else [data]
            releases=[r for r in releases if isinstance(r,dict) and not r.get('draft') and not r.get('prerelease')]
            if not releases:raise ValueError('No stable published releases returned')
            # Release list is newest first; prefer the most recent matching combined Questie bundle.
            if repo.lower()=='questie/questie':
                releases=[r for r in releases if re.search(r'v\d+\.\d+\.\d+\+v\d+\.\d+\.\d+',r.get('tag_name',''))]
                if not releases:raise ValueError('No combined Questie release in response')
            if repo.lower()==RARE_SOURCE:
                releases=[r for r in releases if any(re.fullmatch(r'RareScanner_FOREVER_1\.60\.1[._-]?b\d+\.zip',a.get('name',''),re.I) for a in r.get('assets',[]))]
                if not releases:raise ValueError('No Forever-specific ZIP in recent mirror releases. Retail files will not be installed.')
            data=releases[0]
            assets=[a for a in data.get('assets',[]) if a.get('name','').lower().endswith('.zip') and a.get('size',0)<=MAX_ZIP]
            return {'tag':data.get('tag_name',''), 'assets':assets, 'page':data.get('html_url',''), 'name':data.get('name',''), 'repo':repo}
        except Exception as exc:
            errors.append(f'{endpoint.rsplit("/",1)[-1]}: {type(exc).__name__}: {exc}')
    raise RuntimeError('GitHub release lookup failed. '+' | '.join(errors))

def check_cancel(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise DownloadCancelled('Cancelled before installation')


def safe_extract_zip(blob, target, cancelled=None, progress=None):
    """Validate names, CRC and extract ONCE, in cancellable 256 KiB chunks."""
    target=Path(target).resolve()
    with zipfile.ZipFile(blob) as z:
        members=z.infolist()
        files=[i for i in members if not i.is_dir()]
        total=sum(i.file_size for i in files)
        if len(files)>10000 or total>MAX_ZIP:
            raise ValueError('ZIP is too large')
        for i in members:
            name=i.filename.replace('\\','/')
            parts=name.split('/')
            if (name.startswith('/') or re.match(r'^[A-Za-z]:',name) or
                '..' in parts or any(':' in part for part in parts) or
                (i.external_attr>>16)&0o170000==0o120000):
                raise ValueError('Unsafe ZIP path or symbolic link')
        completed=0
        for i in files:
            check_cancel(cancelled)
            dest=(target/i.filename.replace('\\','/')).resolve()
            if target not in dest.parents:
                raise ValueError('ZIP entry escapes extraction folder')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as incoming, open(dest,'wb') as outgoing:
                while True:
                    check_cancel(cancelled)
                    chunk=incoming.read(256*1024)
                    if not chunk:break
                    outgoing.write(chunk)
                    completed+=len(chunk)
                    if progress:progress(completed,total)
        check_cancel(cancelled)


def backup_base(addons_root):
    """Store backups outside Interface/AddOns, under the WoW client root."""
    root=Path(addons_root).resolve()
    return root.parent.parent/'HinoAddonManager'/'Backups'


def migrate_legacy_backups(addons_root):
    """Move old backups without overwriting or deleting any backup data."""
    root=Path(addons_root).resolve()
    old=root/'_HinoBackups'
    new=backup_base(root)
    if not old.is_dir():
        return
    new.mkdir(parents=True,exist_ok=True)
    for item in old.iterdir():
        destination=new/item.name
        if destination.exists():
            # Keep conflicting legacy backups untouched rather than risk data loss.
            continue
        shutil.move(str(item),str(destination))
    try:
        old.rmdir()  # Only remove the empty legacy directory.
    except OSError:
        pass


def install_staged(folders, addons_root, cancelled=None, progress=None):
    """Copy to hidden destinations before committing; rollback on commit errors.

    Cancellation is honored until commit starts. During the short commit phase,
    cancellation is intentionally deferred to protect installed addons.
    """
    root=Path(addons_root).resolve()
    if not root.is_dir():raise FileNotFoundError('AddOns folder not found')
    folders=list(folders)
    names=[f.name for f in folders]
    if len(set(n.lower() for n in names))!=len(names):
        raise ValueError('Duplicate addon folder names')
    for f in folders:
        if f.is_symlink() or any(child.is_symlink() for child in f.rglob('*')):
            raise ValueError('Addon contains symbolic links: '+str(f))
        if not f.is_dir() or not toc_info(f):
            raise ValueError('Invalid staged addon: '+str(f))
        if f.name in ('.','..','_HinoBackups') or not re.fullmatch(r'[\w .()\-]+',f.name):
            raise ValueError('Unexpected addon folder name: '+f.name)
    stage=root/('_HinoStaging-'+str(time.time_ns()))
    stage.mkdir()
    backed=[]; installed=[]
    backup=backup_base(root)/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000))
    try:
        total=sum(p.stat().st_size for f in folders for p in f.rglob('*') if p.is_file())
        done=0
        for f in folders:
            for p in f.rglob('*'):
                check_cancel(cancelled)
                relative=p.relative_to(f)
                dest=stage/f.name/relative
                if p.is_dir():
                    dest.mkdir(parents=True,exist_ok=True)
                elif p.is_file():
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with open(p,'rb') as inp,open(dest,'wb') as out:
                        while True:
                            check_cancel(cancelled)
                            chunk=inp.read(256*1024)
                            if not chunk:break
                            out.write(chunk);done+=len(chunk)
                            if progress:progress(done,total)
        check_cancel(cancelled)
        # COMMIT: no cancellation checks between moving old and new directories.
        try:
            for f in folders:
                dest=root/f.name
                if dest.exists():
                    backup.mkdir(parents=True,exist_ok=True)
                    previous=backup/f.name
                    if previous.exists():raise FileExistsError(str(previous))
                    dest.rename(previous)
                    backed.append((dest,previous))
                (stage/f.name).rename(dest)
                installed.append(dest)
        except Exception:
            for dest in reversed(installed):
                if dest.exists():shutil.rmtree(dest)
            for dest,previous in reversed(backed):
                if previous.exists():previous.rename(dest)
            raise
        return names,str(backup) if backed else 'No previous files to back up'
    finally:
        shutil.rmtree(stage,ignore_errors=True)


def addon_folders(unpack, cancelled=None, progress=None):
    """Discover addon roots using bounded, cancellable directory traversal."""
    unpack=Path(unpack)
    found=[]
    scanned=0
    for base, dirs, files in os.walk(unpack):
        check_cancel(cancelled)
        scanned+=1
        if scanned>30000:
            raise ValueError('Archive contains too many directories')
        current=Path(base)
        depth=len(current.relative_to(unpack).parts)
        if depth>5:
            dirs[:]=[]
            continue
        tocs=[name for name in files if name.lower().endswith('.toc')]
        if tocs:
            found.append(current)
            dirs[:]=[]
        if progress and scanned%20==0:
            progress(scanned,0)
    if not found:
        raise ValueError('No WoW addon .toc files found in ZIP')
    if progress:progress(scanned,scanned)
    return found

def install_zip(path,addons_root,expected=None):
    root=Path(addons_root).resolve()
    if not root.is_dir():raise FileNotFoundError('AddOns folder not found')
    with tempfile.TemporaryDirectory(prefix='hino-addons-') as td:
        unpack=Path(td)/'unpack';unpack.mkdir()
        safe_extract_zip(path,unpack)
        folders=addon_folders(unpack)
        if expected and expected.lower() not in [f.name.lower() for f in folders]:
            raise ValueError(f'Package does not contain expected addon folder: {expected}.')
        for folder in folders:
            incoming=toc_info(folder)
            previous=toc_info(root/folder.name) if (root/folder.name).is_dir() else None
            if not incoming:raise ValueError('Missing addon TOC: '+folder.name)
            if previous and not compatible_interfaces(previous.get('interface',''),incoming.get('interface','')):
                raise ValueError('Compatibility not verified for '+folder.name+'. Existing and incoming interface codes do not overlap. No files were changed.')
            if not previous and '16001' not in re.findall(r'\b\d{5,6}\b',incoming.get('interface','')):
                raise ValueError('New addon '+folder.name+' does not explicitly declare WoW Forever interface 16001. No files were changed.')
        return install_staged(folders,root)


def version_tuple(v):
    nums=re.findall(r'\d+',v or '')
    return tuple(int(n) for n in nums[:4]) if nums else ()

def classify(item,release):
    if not release or not release.get('tag'):return 'Unable to verify version',None
    if item['name'] in ('Questie','QuestieDB') and re.search(r'v\d+\.\d+\.\d+\+v\d+\.\d+\.\d+',release.get('tag','')):
        assets=[a for a in release['assets'] if re.fullmatch(r'Questie-v[\w.+-]+\.zip',a['name'],re.I)]
        # Prefer official combined package; never guess when multiple plausible packages exist.
        if len(assets)!=1:return 'Review release assets',None
        m=re.search(r'v(\d+\.\d+\.\d+)\+v(\d+\.\d+\.\d+)',release['tag'])
        if not m:return 'Review release version',None
        remote=m.group(1 if item['name']=='Questie' else 2)
        local=item['version']
        if version_tuple(remote)>version_tuple(local):return 'Update available',assets[0]
        return 'Up to date' if version_tuple(remote)==version_tuple(local) else 'Installed newer',None
    if item['name']=='RareScanner' and release.get('repo')==RARE_SOURCE:
        assets=[a for a in release['assets'] if re.fullmatch(r'RareScanner_FOREVER_1\.60\.1[._-]?b\d+\.zip',a.get('name',''),re.I)]
        if not assets:return 'No verified Forever ZIP',None
        # Release tag is the mirror sync timestamp, NOT the addon version.
        def build(a):
            m=re.search(r'1\.60\.1[._-]?b(\d+)',a['name'],re.I)
            return int(m.group(1)) if m else -1
        asset=max(assets,key=build)
        remote=build(asset)
        local_match=re.search(r'1\.60\.1[._-]?b(\d+)',item['version'],re.I)
        if not local_match:return 'Review installed version',None
        local=int(local_match.group(1))
        if remote>local:return 'Update available',asset
        return ('Up to date' if remote==local else 'Installed newer'),None
    asset=candidate_github_asset(item,release)
    if asset:return 'Update available',asset
    # A newer tag alone is not evidence of WoW Forever compatibility.
    # Never silently classify a generic release as current or safe.
    return 'Compatibility unverified',None

class DownloadCancelled(Exception):
    pass

class DownloadTimeout(Exception):
    pass

def download_asset(asset, target, progress=None, cancelled=None, max_seconds=150, opener=secure_open):
    """Download completely into .part before atomic rename; never modify addons here.

    Socket timeout covers stalled reads, wall-clock deadline covers slow endless streams.
    """
    url=asset.get('browser_download_url','')
    if not (url.startswith('https://github.com/') or url.startswith('https://objects.githubusercontent.com/')):
        raise ValueError('Unexpected download host')
    target=Path(target)
    part=target.with_name(target.name+'.part')
    start=time.monotonic();done=0
    try:
        req=urllib.request.Request(url,headers={'User-Agent':UA['User-Agent']})
        with opener(req,timeout=12) as response, open(part,'wb') as dest:
            final_url=response.geturl() if hasattr(response,'geturl') else url
            from urllib.parse import urlsplit
            host=(urlsplit(final_url).hostname or '').lower()
            if host not in ('github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'):
                raise ValueError('Download redirected to an unexpected host: '+host)
            length=response.headers.get('Content-Length') if hasattr(response,'headers') else None
            total=int(length) if length and length.isdigit() else 0
            if total>MAX_ZIP:raise ValueError('Download exceeds maximum ZIP size')
            while True:
                if cancelled is not None and cancelled.is_set():raise DownloadCancelled('Download cancelled by user')
                if time.monotonic()-start>max_seconds:raise DownloadTimeout(f'Download exceeded {max_seconds} seconds')
                try:chunk=response.read(128*1024)
                except (socket.timeout,TimeoutError) as e:raise DownloadTimeout('No data received before network timeout') from e
                if not chunk:break
                done+=len(chunk)
                if done>MAX_ZIP:raise ValueError('Download too large')
                dest.write(chunk)
                if progress:progress(done,total)
        if cancelled is not None and cancelled.is_set():raise DownloadCancelled('Download cancelled by user')
        if not zipfile.is_zipfile(part):raise ValueError('Downloaded file is not a valid ZIP archive')
        os.replace(part,target)
        return done
    finally:
        if part.exists():part.unlink()

class GUI:
 def __init__(self,root):
    self.root=root;root.title('Hino Addon Manager V4.0.1 · WoW Forever');root.geometry('1100x740');root.minsize(880,570)
    self.cfg=load_config();self.items=[];self.busy=False;self.results={};self.cancel_event=threading.Event();self.update_in_progress=False;self.expanded_addon=None;self.collapsed_groups={'Bagnon family','GearQuest Forever','Questie + QuestieDB','Polestar Guides'};self.backup_paths=[];self._backup_loaded=False;self._backup_loading=False;self._backup_request=0
    # V3.7 visual system: editorial, charcoal-and-ivory desktop workspace.
    # Intentionally replaces the old green sidebar and dashboard identity.
    self.bg='#0c1018';self.panel='#161c28';self.panel2='#202939';self.fg='#f4f7fc';self.green='#91b7ff';self.muted='#91a0b6';self.edge='#293444'
    bg=self.bg;panel=self.panel;fg=self.fg;green=self.green;muted=self.muted;edge=self.edge
    root.configure(bg=bg)
    style=ttk.Style();style.theme_use('clam')
    style.configure('Treeview',background=panel,foreground=fg,fieldbackground=panel,rowheight=49,borderwidth=0,font=('Segoe UI',10))
    style.map('Treeview',background=[('selected','#273f63')],foreground=[('selected','#f4f7fc')])
    style.configure('Treeview.Heading',background='#1b2432',foreground='#98a9bc',relief='flat',font=('Segoe UI',9,'bold'),padding=(11,13))
    style.configure('TButton',font=('Segoe UI',10),padding=(13,10),background='#263143',foreground=fg,borderwidth=0)
    style.map('TButton',background=[('active','#32445c'),('disabled','#202939')],foreground=[('disabled','#777780')])
    style.configure('Primary.TButton',font=('Segoe UI',10,'bold'),padding=(17,11),background='#91b7ff',foreground='#101829')
    style.map('Primary.TButton',background=[('active','#b7d0ff')])
    style.configure('TCombobox',fieldbackground='#202939',background='#202939',foreground='#f4f7fc')
    style.configure('Horizontal.TProgressbar',troughcolor='#263143',background=green,borderwidth=0)
    self.shell=tk.Frame(root,bg=bg);self.shell.pack(fill='both',expand=True)
    # V3.9: the addon list IS the home screen. Navigation is deliberately minimal.
    top=tk.Frame(self.shell,bg=bg)
    top.pack(fill='x',padx=28,pady=(20,8))
    tk.Label(top,text='hino',bg=bg,fg=fg,font=('Segoe UI',21,'bold')).pack(side='left')
    tk.Label(top,text='  addon manager',bg=bg,fg=muted,font=('Segoe UI',10)).pack(side='left',pady=(7,0))
    ttk.Button(top,text='Settings  ⚙',command=lambda:self.show_page('settings')).pack(side='right')
    bar=tk.Frame(self.shell,bg=bg)
    bar.pack(fill='x',padx=27,pady=(0,12))
    self.nav_buttons={}
    for key,title in [('addons','My Addons'),('curseforge','Discover')]:
        btn=tk.Button(bar,text=title,font=('Segoe UI',11,'bold'),bg=bg,fg=muted,activebackground=panel,activeforeground=fg,bd=0,relief='flat',padx=15,pady=9,command=lambda k=key:self.show_page(k),cursor='hand2')
        btn.pack(side='left',padx=(0,8));self.nav_buttons[key]=btn
    tk.Frame(self.shell,bg=edge,height=1).pack(fill='x',padx=28,pady=(0,16))
    main=tk.Frame(self.shell,bg=bg);main.pack(fill='both',expand=True)
    header=tk.Frame(main,bg=bg);header.pack(fill='x',padx=30,pady=(0,12))
    self.page_title=tk.StringVar(value='My Addons')
    tk.Label(header,textvariable=self.page_title,bg=bg,fg=fg,font=('Segoe UI',21,'bold')).pack(side='left')
    self.pages={}
    content=tk.Frame(main,bg=bg);content.pack(fill='both',expand=True,padx=36)
    for key in ('dashboard','addons','updates','backups','history','curseforge','settings'):
        self.pages[key]=tk.Frame(content,bg=bg)
    self.path=tk.StringVar(value=self.cfg.get('wow','D:/World of Warcraft/_classic_beta_'))
    self.overview=tk.StringVar(value='Scanning addons...')
    # Dashboard: left-side curated activity, right-side quiet status rail.
    dash=self.pages['dashboard']
    self.installed_text=tk.StringVar(value='—');self.updates_text=tk.StringVar(value='—');self.backup_text=tk.StringVar(value='0')
    dashboard_body=tk.Frame(dash,bg=bg);dashboard_body.pack(fill='both',expand=True)
    left=tk.Frame(dashboard_body,bg=bg);left.pack(side='left',fill='both',expand=True,padx=(0,22))
    right=tk.Frame(dashboard_body,bg=bg,width=280);right.pack(side='right',fill='y');right.pack_propagate(False)
    hero=tk.Frame(left,bg=panel,padx=24,pady=23,highlightbackground=edge,highlightthickness=1)
    hero.pack(fill='x',pady=(0,23))
    tk.Label(hero,text='YOUR WORLD, ORGANIZED',bg=panel,fg=green,font=('Segoe UI',9,'bold')).pack(anchor='w')
    tk.Label(hero,text='Everything in its place.',bg=panel,fg=fg,font=('Segoe UI',21,'bold')).pack(anchor='w',pady=(8,6))
    tk.Label(hero,text='Find, manage and update your WoW Forever addons.\nWithout the clutter.',bg=panel,fg=muted,font=('Segoe UI',11),justify='left').pack(anchor='w',pady=(0,18))
    hero_actions=tk.Frame(hero,bg=panel);hero_actions.pack(anchor='w')
    ttk.Button(hero_actions,text='Check for updates  →',style='Primary.TButton',command=self.check_all).pack(side='left',padx=(0,9))
    ttk.Button(hero_actions,text='Browse addons',command=lambda:self.show_page('curseforge')).pack(side='left')
    dash_addons_header=tk.Frame(left,bg=bg);dash_addons_header.pack(fill='x',pady=(0,10))
    tk.Label(dash_addons_header,text='Your collection',bg=bg,fg=fg,font=('Segoe UI',14,'bold')).pack(side='left')
    ttk.Button(dash_addons_header,text='View all  →',command=lambda:self.show_page('addons')).pack(side='right')
    self.addon_cards=tk.Frame(left,bg=bg);self.addon_cards.pack(fill='x')
    self.dashboard_more=tk.StringVar(value='')
    tk.Label(left,textvariable=self.dashboard_more,bg=bg,fg=muted,font=('Segoe UI',9),anchor='w').pack(fill='x',pady=(12,0))
    tk.Label(right,text='AT A GLANCE',bg=bg,fg=muted,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(2,12))
    for caption,var,marker in [('Installed packages',self.installed_text,'◫'),('Updates ready',self.updates_text,'↗'),('Local backups',self.backup_text,'◷')]:
        card=tk.Frame(right,bg=panel,padx=19,pady=17,highlightbackground=edge,highlightthickness=1)
        card.pack(fill='x',pady=(0,10))
        tk.Label(card,text=marker,bg=panel,fg=green,font=('Segoe UI',18)).pack(side='right')
        tk.Label(card,text=caption,bg=panel,fg=muted,font=('Segoe UI',10)).pack(anchor='w')
        tk.Label(card,textvariable=var,bg=panel,fg=fg,font=('Segoe UI',25,'bold')).pack(anchor='w',pady=(4,0))
    tk.Label(right,text='QUICK ACTIONS',bg=bg,fg=muted,font=('Segoe UI',9,'bold')).pack(anchor='w',pady=(19,11))
    ttk.Button(right,text='Install from ZIP  ↗',command=self.local_zip).pack(fill='x',pady=(0,8))
    ttk.Button(right,text='Review updates  →',command=lambda:self.show_page('updates')).pack(fill='x')
    # One search field and two common actions, nothing else on the main screen.
    addons=self.pages['addons']
    toolbar=tk.Frame(addons,bg=bg);toolbar.pack(fill='x',pady=(0,13))
    self.search_text=tk.StringVar()
    searchbox=tk.Entry(toolbar,textvariable=self.search_text,bg=self.panel2,fg=fg,insertbackground=fg,
                       relief='flat',font=('Segoe UI',11))
    searchbox.pack(side='left',fill='x',expand=True,ipady=10,padx=(0,12))
    self.search_placeholder='Search installed addons...'
    def search_focus_in(event):
        if searchbox.get()==self.search_placeholder:
            searchbox.delete(0,'end');searchbox.configure(fg=self.fg)
    def search_focus_out(event):
        if not searchbox.get():
            searchbox.insert(0,self.search_placeholder);searchbox.configure(fg=self.muted)
    searchbox.insert(0,self.search_placeholder);searchbox.configure(fg=self.muted)
    searchbox.bind('<FocusIn>',search_focus_in);searchbox.bind('<FocusOut>',search_focus_out)
    self.search_text.trace_add('write',lambda *_:self.render_addon_list())
    ttk.Button(toolbar,text='Check updates',command=self.check_all).pack(side='left',padx=(0,9))
    ttk.Button(toolbar,text='+ Add addon',style='Primary.TButton',command=self.add_addon_menu).pack(side='left',padx=(0,9))
    ttk.Button(toolbar,text='Update all',command=self.update_all).pack(side='left')
    self.provider_filter=tk.StringVar(value='All providers')
    self.status_filter=tk.StringVar(value='All statuses')
    self.library_hint=tk.StringVar(value='Loading your addons...')
    tk.Label(addons,textvariable=self.library_hint,bg=bg,fg=muted,font=('Segoe UI',10),anchor='w').pack(fill='x',pady=(0,10))
    tablebox=tk.Frame(addons,bg=bg);tablebox.pack(fill='both',expand=True)
    self.tree=ttk.Treeview(tablebox,columns=('title','version','latest','interface','source','status','action'),show='tree headings',selectmode='browse')
    self.tree.heading('#0',text='PACKAGE')
    self.tree.column('#0',width=140,minwidth=110,stretch=False)
    self.table_sort=('title',False)
    for col,label,width in [('title','ADDON',235),('version','INSTALLED',105),('latest','LATEST',115),('interface','CLIENT',85),('source','SOURCE',110),('status','STATUS',170),('action','ACTION',100)]:
        self.tree.heading(col,text=label,command=lambda c=col:self.sort_addons(c))
        self.tree.column(col,width=width,minwidth=85,stretch=col in ('title','status'))
    scroll=ttk.Scrollbar(tablebox,orient='vertical',command=self.tree.yview)
    self.tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right',fill='y');self.tree.pack(side='left',fill='both',expand=True)
    self.tree.bind('<Double-1>',lambda e:self.show_selected_details())
    self.tree.bind('<ButtonRelease-1>',self.on_tree_click,add='+')
    self.search_text.trace_add('write',lambda *_:self.render_addon_list())
    # Power-user actions are on the right-click menu, not a permanent button row.
    self.addon_menu=tk.Menu(root,tearoff=0,bg=self.panel,fg=self.fg,activebackground=self.panel2,activeforeground=self.fg)
    self.addon_menu.add_command(label='Update selected addon',command=self.update)
    self.addon_menu.add_command(label='Check selected version',command=self.check)
    self.addon_menu.add_command(label='Addon details',command=self.show_selected_details)
    self.addon_menu.add_separator()
    self.addon_menu.add_command(label='Open project page',command=self.open_selected_provider)
    self.addon_menu.add_command(label='Set GitHub source',command=self.set_source)
    self.tree.bind('<Button-3>',self.popup_addon_menu)
    # Updates: update workflow, release information and manual RareScanner access.
    upd=self.pages['updates']
    tk.Label(upd,text='Only releases passing package checks can be installed; check provider and client compatibility before applying.',bg=bg,fg=muted,font=('Segoe UI',11)).pack(anchor='w',pady=(0,18))
    ubox=tk.Frame(upd,bg=panel,padx=20,pady=20,highlightbackground=edge,highlightthickness=1);ubox.pack(fill='x')
    top=tk.Frame(ubox,bg=panel);top.pack(fill='x')
    tk.Label(top,text='Addon updates',bg=panel,fg=fg,font=('Segoe UI',15,'bold')).pack(side='left')
    self.update_count_badge=tk.StringVar(value='0 available')
    tk.Label(top,textvariable=self.update_count_badge,bg='#353029',fg=green,padx=12,pady=5,font=('Segoe UI',10,'bold')).pack(side='right')
    tk.Label(ubox,text='Check compatible releases, then review before installing. Related addon modules are updated together when their package source is verified.',bg=panel,fg=muted,wraplength=820,justify='left').pack(anchor='w',pady=(9,14))
    ur=tk.Frame(ubox,bg=panel);ur.pack(fill='x')
    ttk.Button(ur,text='Check updates',style='Primary.TButton',command=self.check_all).pack(side='left',padx=(0,10))
    self.install_updates_button=ttk.Button(ur,text='Install updates',command=self.update_all,state='disabled')
    self.install_updates_button.pack(side='left')
    self.update_detail=tk.StringVar(value='Check for updates to see available versions.')
    tk.Label(upd,textvariable=self.update_detail,bg=bg,fg=muted,justify='left',wraplength=850,font=('Segoe UI',10)).pack(anchor='w',pady=(12,8))
    update_container=tk.Frame(upd,bg=bg);update_container.pack(fill='both',expand=True,pady=(0,8))
    self.update_canvas=tk.Canvas(update_container,bg=bg,highlightthickness=0)
    update_scroll=ttk.Scrollbar(update_container,orient='vertical',command=self.update_canvas.yview)
    self.update_canvas.configure(yscrollcommand=update_scroll.set)
    update_scroll.pack(side='right',fill='y');self.update_canvas.pack(side='left',fill='both',expand=True)
    self.update_list=tk.Frame(self.update_canvas,bg=bg)
    self.update_window=self.update_canvas.create_window((0,0),window=self.update_list,anchor='nw')
    self.update_list.bind('<Configure>',lambda e:self.update_canvas.configure(scrollregion=self.update_canvas.bbox('all')))
    self.update_canvas.bind('<Configure>',lambda e:self.update_canvas.itemconfigure(self.update_window,width=e.width))
    self.update_canvas.bind('<MouseWheel>',lambda e:(self.update_canvas.yview_scroll(-int(e.delta/120),'units'),'break')[1])
    # Backups: browse the actual safe location and restore.
    backups=self.pages['backups']
    tk.Label(backups,text='Backups are stored outside Interface\\AddOns.',bg=bg,fg=muted,font=('Segoe UI',11)).pack(anchor='w',pady=(0,12))
    self.backup_location=tk.StringVar()
    tk.Label(backups,textvariable=self.backup_location,bg=panel,fg=fg,padx=14,pady=13,anchor='w',wraplength=730,justify='left').pack(fill='x')
    backup_actions=tk.Frame(backups,bg=bg);backup_actions.pack(fill='x',pady=14)
    ttk.Button(backup_actions,text='Restore backup',style='Primary.TButton',command=self.restore_backup).pack(side='left',padx=(0,9))
    ttk.Button(backup_actions,text='Open backup folder',command=self.open_backups).pack(side='left',padx=(0,9))
    ttk.Button(backup_actions,text='Refresh backups',command=self.refresh_backups).pack(side='left')
    self.backup_list=tk.Listbox(backups,bg=panel,fg=fg,selectbackground='#273f63',relief='flat',font=('Segoe UI',11),height=9,activestyle='none')
    self.backup_list.pack(fill='x',pady=(0,10))
    ttk.Button(backup_actions,text='Delete selected backup',command=self.delete_backup).pack(side='left',padx=(9,0))
    tk.Label(backups,text='Select a backup above to restore or delete it. Deleting a backup cannot be undone.',bg=bg,fg=muted,font=('Segoe UI',9)).pack(anchor='w')
    # History is a local, append-only record of successful operations and errors.
    hist=self.pages['history']
    tk.Label(hist,text='Recent addon installs, updates and restores. Stored on this PC.',bg=bg,fg=muted,font=('Segoe UI',11)).pack(anchor='w',pady=(0,14))
    ttk.Button(hist,text='Refresh history',command=self.render_history).pack(anchor='w',pady=(0,12))
    self.history_list=tk.Listbox(hist,bg=panel,fg=fg,selectbackground='#273f63',relief='flat',font=('Segoe UI',11),activestyle='none')
    self.history_list.pack(fill='both',expand=True)
    # CurseForge discovery: read-only metadata; no automatic CurseForge downloads.
    cf=self.pages['curseforge']
    tk.Label(cf,text='Search CurseForge. Select an addon to view its available releases.',bg=bg,fg=muted,font=('Segoe UI',11)).pack(anchor='w',pady=(0,15))
    cfrow=tk.Frame(cf,bg=bg);cfrow.pack(fill='x',pady=(0,10))
    self.cf_query=tk.StringVar()
    tk.Entry(cfrow,textvariable=self.cf_query,bg=self.panel2,fg=fg,insertbackground=fg,font=('Segoe UI',11),relief='flat').pack(side='left',fill='x',expand=True,ipady=8)
    ttk.Button(cfrow,text='Search',style='Primary.TButton',command=self.cf_do_search).pack(side='left',padx=(10,0))
    browser=tk.PanedWindow(cf,orient='vertical',bg=self.bg,sashwidth=6,bd=0,showhandle=False)
    browser.pack(fill='both',expand=True)
    results=tk.Frame(browser,bg=bg)
    self.cf_tree=ttk.Treeview(results,columns=('id','name'),show='headings',height=8)
    for col,label,width in [('id','PROJECT ID',125),('name','ADDON',560)]:
        self.cf_tree.heading(col,text=label);self.cf_tree.column(col,width=width,stretch=col=='name')
    self.cf_tree.pack(fill='both',expand=True)
    browser.add(results,minsize=140)
    details=tk.Frame(browser,bg=panel,padx=16,pady=12,highlightbackground=edge,highlightthickness=1)
    detail_heading=tk.Frame(details,bg=panel);detail_heading.pack(fill='x',pady=(0,8))
    tk.Label(detail_heading,text='Release details',bg=panel,fg=fg,font=('Segoe UI',12,'bold')).pack(side='left')
    ttk.Button(detail_heading,text='View selected files',command=self.cf_show_files).pack(side='right')
    self.cf_info=tk.StringVar(value='Search CurseForge, then select an addon to inspect its Forever releases.')
    tk.Label(details,textvariable=self.cf_info,bg=panel,fg=muted,wraplength=700,justify='left',anchor='w').pack(fill='x',pady=(0,7))
    self.cf_detail_text=tk.Text(details,height=6,bg=panel,fg=fg,relief='flat',bd=0,font=('Consolas',10),wrap='word',state='disabled',insertbackground=fg)
    self.cf_detail_text.pack(fill='both',expand=True)
    browser.add(details,minsize=155)
    # Double-click a result to load versions, without requiring a modal popup.
    self.cf_tree.bind('<Double-1>',lambda event:self.cf_show_files())
    # Settings: no more technical buttons cluttering dashboard.
    settings=self.pages['settings']
    tk.Label(settings,text='GAME LOCATION',bg=bg,fg=muted,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(0,7))
    location=tk.Frame(settings,bg=panel,padx=12,pady=12);location.pack(fill='x')
    tk.Entry(location,textvariable=self.path,bg='#1b2432',fg=fg,insertbackground=fg,relief='flat',font=('Segoe UI',10)).pack(side='left',fill='x',expand=True,ipady=8)
    ttk.Button(location,text='Browse',command=self.browse).pack(side='left',padx=(9,0))
    ttk.Button(location,text='Save & scan',command=self.refresh).pack(side='left',padx=(8,0))
    tk.Label(settings,text='UPDATE PREFERENCES',bg=bg,fg=muted,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(24,9))
    self.auto_check=tk.BooleanVar(value=self.cfg.get('auto_check',True))
    tk.Checkbutton(settings,text='Automatically check linked addon sources on launch and every 6 hours',variable=self.auto_check,command=self.save_preferences,bg=bg,fg=fg,selectcolor='#1b2432',activebackground=bg,activeforeground=fg,font=('Segoe UI',10)).pack(anchor='w')
    tk.Label(settings,text='All installed folders are scanned; only identified sources can be checked online. Downloads require verified compatibility.',bg=bg,fg=muted).pack(anchor='w',pady=(4,0))
    ttk.Button(settings,text='Export addon source report',command=self.export_source_report).pack(anchor='w',pady=(12,0))
    tk.Label(settings,text='CURSEFORGE 3RD PARTY API',bg=bg,fg=muted,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(24,8))
    self.cf_key=tk.StringVar()  # Stored only in Windows Credential Manager when user opts in.
    try:self.cf_key.set(load_cf_credential())
    except Exception:pass
    cfkeyrow=tk.Frame(settings,bg=bg);cfkeyrow.pack(fill='x')
    tk.Entry(cfkeyrow,textvariable=self.cf_key,show='•',bg=self.panel2,fg=fg,insertbackground=fg,relief='flat',font=('Segoe UI',11)).pack(side='left',fill='x',expand=True,ipady=7)
    ttk.Button(cfkeyrow,text='Test connection',command=self.cf_test).pack(side='left',padx=(9,0))
    ttk.Button(cfkeyrow,text='Save securely',command=self.cf_save_key).pack(side='left',padx=(9,0))
    ttk.Button(cfkeyrow,text='Forget key',command=self.cf_forget_key).pack(side='left',padx=(9,0))
    tk.Label(settings,text='Save securely stores the key in Windows Credential Manager for this Windows user; Forget key deletes it.\nCurseForge downloads remain disabled pending distribution permissions.',bg=bg,fg=muted,justify='left').pack(anchor='w',pady=(6,0))
    tk.Label(settings,text='ADVANCED' ,bg=bg,fg=muted,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(24,9))
    advanced=tk.Frame(settings,bg=bg);advanced.pack(fill='x')
    ttk.Button(advanced,text='Test GitHub connection',command=self.test_connection).pack(side='left',padx=(0,9))
    ttk.Button(advanced,text='Link known sources',command=self.autolink).pack(side='left')
    tk.Label(settings,text='TOOLS & RECOVERY',bg=bg,fg=muted,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(22,10))
    extra=tk.Frame(settings,bg=bg);extra.pack(fill='x')
    for title,key in [('Backups','backups'),('History','history'),('Update details','updates')]:
        ttk.Button(extra,text=title,command=lambda k=key:self.show_page(k)).pack(side='left',padx=(0,9))
    tk.Label(settings,text='APPLICATION UPDATES',bg=bg,fg=muted,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(24,8))
    ttk.Button(settings,text='Check Hino app update',command=self.check_app_update).pack(anchor='w')
    tk.Label(settings,text='App updates come from official GitHub Releases, separate from addon updates.',bg=bg,fg=muted).pack(anchor='w',pady=(5,0))
    ttk.Button(settings,text='Open addon folder',command=self.open_folder).pack(anchor='w',pady=(12,0))

    # Shared drop zone and progress footer visible on every page.
    self.drop=tk.Label(main,text='Drop an addon ZIP here to install  ·  or choose Install ZIP',bg=panel,fg=muted,font=('Segoe UI',9),pady=10,highlightbackground=edge,highlightthickness=1)
    # Legacy drag-drop widget intentionally not packed; Add addon is the entry point.
    if DND_FILES:
        for target in (root,self.drop):
            target.drop_target_register(DND_FILES);target.dnd_bind('<<Drop>>',self.handle_drop)
    else:self.drop.configure(text='Optional drag and drop: install tkinterdnd2')
    progressrow=tk.Frame(main,bg=bg);progressrow.pack(fill='x',padx=24,pady=(0,10))
    self.progress=ttk.Progressbar(progressrow,mode='determinate',maximum=100)
    self.progress.pack(side='left',fill='x',expand=True,padx=(0,12))
    self.progress_label=tk.StringVar(value='Ready')
    tk.Label(progressrow,textvariable=self.progress_label,bg=bg,fg=green,width=30,anchor='w').pack(side='left')
    self.cancel_button=ttk.Button(progressrow,text='Cancel',command=self.cancel_download,state='disabled');self.cancel_button.pack(side='left')
    self.status=tk.StringVar(value='Ready to scan your addons.')
    tk.Label(main,textvariable=self.status,bg=panel,fg=muted,anchor='w',wraplength=920,padx=24,pady=12,font=('Segoe UI',9)).pack(fill='x')
    self.show_page('addons')
    root.after(100,self.refresh)
    if self.auto_check.get():root.after(3000,self.check_all)
    root.after(6*60*60*1000,self.periodic_update_check)
    if getattr(sys, "frozen", False):root.after(7500,self.check_app_update_silently)

 def check_app_update_silently(self):
    self._check_hino_update(silent=True)

 def check_app_update(self):
    self._check_hino_update(silent=False)

 def _check_hino_update(self, silent=False):
    # Never block Tk or perform installs without user consent.
    if getattr(self,'_hino_update_checking',False):return
    self._hino_update_checking=True
    def worker():
        try:result,error=selfupdate.check_latest(),None
        except Exception as exc:result,error=None,str(exc)
        def done():
            self._hino_update_checking=False
            if error:
                if not silent:messagebox.showerror(APP,'App update check failed: '+error)
                return
            if not result:
                if not silent:messagebox.showinfo(APP,'Hino is up to date (v'+selfupdate.APP_VERSION+').')
                return
            if messagebox.askyesno(APP,'Hino '+result['version']+' is available.\n\nDownload the installer, verify its SHA256 checksum, and update Hino?\n\nYour WoW addons and settings will be preserved.'):
                self._apply_hino_update(result)
        self.root.after(0,done)
    threading.Thread(target=worker,daemon=True).start()

 def _apply_hino_update(self, release):
    self.status.set('Downloading and verifying Hino application update...')
    def worker():
        try:installer,error=selfupdate.stage_installer(release),None
        except Exception as exc:installer,error=None,str(exc)
        def done():
            if error:
                self.status.set('Hino application update failed; existing app unchanged.')
                messagebox.showerror(APP,'Update verification failed: '+error)
                return
            try:selfupdate.run_installer(installer)
            except Exception as exc:
                messagebox.showerror(APP,'Could not launch installer: '+str(exc));return
            self.root.destroy()
        self.root.after(0,done)
    threading.Thread(target=worker,daemon=True).start()

 def cf_save_key(self):
    try:
        save_cf_credential(self.cf_key.get())
        self.status.set('CurseForge API key saved in Windows Credential Manager for this user.')
    except Exception as exc:
        messagebox.showerror(APP,'Could not securely save key: '+str(exc))

 def cf_forget_key(self):
    try:
        delete_cf_credential()
        self.cf_key.set('')
        self.status.set('CurseForge API key removed from Windows Credential Manager.')
    except Exception as exc:
        messagebox.showerror(APP,'Could not forget key: '+str(exc))

 def cf_test(self):
    if self.busy:return
    key=self.cf_key.get()
    def done(data,error):
        self.busy=False
        if error:self.status.set('CurseForge connection failed: '+error);messagebox.showerror(APP,error)
        else:self.status.set('CurseForge authentication succeeded (metadata-only).');messagebox.showinfo(APP,'CurseForge API connection successful. No files were downloaded.')
    self.task(lambda:cf_request(key,'/games/1'),done)

 def cf_do_search(self):
    if self.busy:return
    key=self.cf_key.get();query=self.cf_query.get()
    self.cf_info.set('Searching CurseForge...')
    self.cf_detail_text.configure(state='normal');self.cf_detail_text.delete('1.0','end');self.cf_detail_text.configure(state='disabled')
    def done(data,error):
        self.busy=False
        if error:self.cf_info.set('Search failed: '+error);return
        self.cf_tree.delete(*self.cf_tree.get_children())
        for x in data:self.cf_tree.insert('','end',values=(x['id'],x['name']))
        self.cf_info.set(f'{len(data)} matching projects. Project names alone do not prove WoW Forever compatibility.')
    self.task(lambda:cf_search(key,query),done)

 def cf_show_files(self):
    if self.busy:return
    sel=self.cf_tree.selection()
    if not sel:messagebox.showinfo(APP,'Select a CurseForge project first.');return
    project=str(self.cf_tree.item(sel[0],'values')[0]);key=self.cf_key.get()
    self.cf_info.set('Checking published file metadata...')
    def done(data,error):
        self.busy=False
        if error:self.cf_info.set('File lookup failed: '+error);return
        matches=[f for f in data if cf_forever_evidence(f)]
        self.cf_info.set(f'Project {project}: {len(data)} files inspected; {len(matches)} explicitly mention Forever / 1.60.1. No automatic downloads.')
        lines=[f"{f['name']}    |    {', '.join(map(str,f['versions']))}" for f in matches[:20]]
        self.cf_detail_text.configure(state='normal')
        self.cf_detail_text.delete('1.0','end')
        self.cf_detail_text.insert('end','\n'.join(lines) if lines else 'No explicitly Forever-labelled files were found. Compatibility is unverified.')
        self.cf_detail_text.configure(state='disabled')
    self.task(lambda:cf_files(key,project),done)

 def periodic_update_check(self):
    # Schedule the next pass even if this pass finds an ongoing operation.
    self.root.after(6*60*60*1000,self.periodic_update_check)
    if self.auto_check.get() and not self.busy and self.items:
        self.check_all()

 def add_addon_menu(self):
    """The two install paths, presented only when the user asks to add an addon."""
    popup=tk.Menu(self.root,tearoff=0,bg=self.panel,fg=self.fg,activebackground=self.panel2,activeforeground=self.fg)
    popup.add_command(label='Find addons on CurseForge',command=lambda:self.show_page('curseforge'))
    popup.add_command(label='Install a downloaded ZIP',command=self.local_zip)
    try:
        x=self.root.winfo_pointerx();y=self.root.winfo_pointery()
        popup.tk_popup(x,y)
    finally:popup.grab_release()

 def popup_addon_menu(self,event):
    row=self.tree.identify_row(event.y)
    if not row:return
    self.tree.selection_set(row)
    try:self.addon_menu.tk_popup(event.x_root,event.y_root)
    finally:self.addon_menu.grab_release()

 def show_page(self,key):
    for page in self.pages.values():page.pack_forget()
    self.pages[key].pack(fill='both',expand=True)
    if key=='history' and hasattr(self,'history_list'):self.render_history()
    self.page_title.set({'dashboard':'Overview','addons':'My Addons','updates':'Updates','backups':'Backups','history':'Activity history','curseforge':'Discover addons','settings':'Settings'}[key])
    for k,btn in self.nav_buttons.items():btn.configure(bg=self.panel2 if k==key else self.bg,fg=self.green if k==key else self.muted)
    if key=='backups' and not self._backup_loaded:self.refresh_backups()

 def save_preferences(self):
    self.cfg['auto_check']=bool(self.auto_check.get());save_config(self.cfg)

 def refresh_backups(self):
    """Read backup metadata on a worker, then update Tk only on the UI thread."""
    if self._backup_loading:return
    self._backup_loading=True
    self._backup_request+=1
    request=self._backup_request
    self.backup_location.set('Loading backups…')
    wow_path=self.path.get()
    def worker():
        try:
            root=resolve_wow(wow_path)/'Interface'/'AddOns'
            folder=backup_base(root)
            paths=sorted((p for p in folder.iterdir() if p.is_dir()),key=lambda p:p.name,reverse=True) if folder.exists() else []
            rows=[]
            for path in paths:
                addons=[p.name for p in path.iterdir() if p.is_dir() and toc_info(p)]
                date=path.name[:8];clock=path.name[9:15]
                readable=f'{date[6:8]}/{date[4:6]}/{date[:4]}  {clock[:2]}:{clock[2:4]}:{clock[4:6]}' if len(date)==8 and date.isdigit() and len(clock)==6 and clock.isdigit() else path.name
                rows.append(readable+'  •  '+(', '.join(addons) if addons else 'No addon folders detected'))
            result=(folder,paths,rows,None)
        except Exception as exc:
            result=(None,[],[],str(exc))
        def apply():
            if request!=self._backup_request:return
            folder,paths,rows,error=result
            self._backup_loading=False
            if error:
                self.backup_location.set('Unable to list backups: '+error)
                return
            self.backup_location.set(str(folder))
            self.backup_paths=paths
            self.backup_list.delete(0,'end')
            for row in rows:self.backup_list.insert('end',row)
            self.backup_text.set(str(len(paths)))
            self._backup_loaded=True
        self.root.after(0,apply)
    threading.Thread(target=worker,daemon=True).start()

 def delete_backup(self):
    if self.busy:messagebox.showwarning(APP,'Wait until the current operation finishes.');return
    selection=self.backup_list.curselection()
    if not selection:messagebox.showinfo(APP,'Select a backup first.');return
    path=self.backup_paths[selection[0]]
    root=backup_base(resolve_wow(self.path.get())/'Interface'/'AddOns').resolve()
    if path.resolve().parent!=root:messagebox.showerror(APP,'Invalid backup location.');return
    if not messagebox.askyesno(APP,'Permanently delete this backup?\n\n'+path.name+'\n\nThis cannot be undone.'):return
    try:shutil.rmtree(path);self.refresh_backups();self.status.set('Deleted backup '+path.name)
    except Exception as exc:messagebox.showerror(APP,'Could not delete backup: '+str(exc))

 def open_backups(self):
    folder=backup_base(resolve_wow(self.path.get())/'Interface'/'AddOns')
    folder.mkdir(parents=True,exist_ok=True)
    if hasattr(os,'startfile'):os.startfile(folder)
    else:messagebox.showinfo(APP,str(folder))

 def latest_display(self,item):
    result=self.results.get(item['name'],{})
    if result.get('cf_metadata_only'):
        f=result.get('latest_cf_file')
        if not f:return '—'
        v=cf_file_version(f)
        if not v:return 'Unverified'
        return '.'.join(map(str,v))
    release=result.get('release') or {}
    if result.get('status')=='Update available' and result.get('asset'):
        if item['name'] in ('Questie','QuestieDB'):
            m=re.search(r'v(\d+\.\d+\.\d+)\+v(\d+\.\d+\.\d+)',release.get('tag',''))
            if m:return m.group(1 if item['name']=='Questie' else 2)
        return str(release.get('tag') or 'Unverified')[:32]
    if result.get('status')=='Up to date':return str(item.get('version','—'))
    return '—'

 def can_install_update(self,item):
    result=self.results.get(item['name'],{})
    return bool(result.get('status')=='Update available' and result.get('asset')
                and result.get('release') and not result.get('cf_metadata_only')
                and self.cfg.get('sources',{}).get(item['name']))

 def visible_update_status(self,item):
    if self.can_install_update(item):return 'Ready to update'
    if self.results.get(item['name'],{}).get('status')=='Update available':return 'New version · manual'
    return self.addon_status(item)

 def update_selected_row(self,item):
    if self.can_install_update(item):
        self.update_all({'Questie','QuestieDB'} if item['name'] in ('Questie','QuestieDB') else {item['name']})
    else:
        messagebox.showinfo(APP,'Automatic installation is not available for this addon. CurseForge metadata is read-only; use the official download and Install ZIP after verifying compatibility.')

 def on_tree_click(self,event):
    if self.tree.identify_column(event.x)!='#7':return
    row=self.tree.identify_row(event.y)
    if not row:return 'break'
    if row.startswith('pkg:'):
        members=package_groups(self.items).get(row[4:],[])
        eligible=next((i for i in members if self.can_install_update(i)),None)
        if eligible:self.update_selected_row(eligible)
    else:
        try:item=self.items[int(row)]
        except (ValueError,IndexError):return 'break'
        if self.can_install_update(item):self.update_selected_row(item)
    return 'break'

 def addon_status(self,item):
    result=self.results.get(item['name'],{})
    status=result.get('status')
    if status:return simple_status(status)
    return 'Check required'

 def scroll_addons(self,event,direction=None):
    if direction is None:
        direction=-1 if event.delta>0 else 1
        if abs(event.delta)>=120:direction*=max(1,abs(event.delta)//120)
    self.addon_canvas.yview_scroll(int(direction),'units')
    return 'break'

 def bind_addon_scroll(self,widget):
    # Bind the wheel on cards and their children, not globally across pages.
    widget.bind('<MouseWheel>',self.scroll_addons)
    widget.bind('<Button-4>',lambda e:self.scroll_addons(e,-1))
    widget.bind('<Button-5>',lambda e:self.scroll_addons(e,1))
    for child in widget.winfo_children():self.bind_addon_scroll(child)

 def provider_for(self,item):
    if addon_group(item)=='Polestar Guides':return 'CurseForge'
    repo=self.cfg.get('sources',{}).get(item['name'],'')
    if repo==RARE_SOURCE:return 'CurseForge'
    if repo:return 'GitHub'
    identity=declared_provider(item)
    return {'curseforge':'CurseForge','github':'GitHub','wago':'Wago','wowinterface':'WoWInterface'}.get(identity['provider'],'Unidentified')

 def sort_addons(self,column):
    old,reverse=self.table_sort
    self.table_sort=(column,not reverse if column==old else False)
    self.render_addon_list()

 def render_addon_list(self):
    if not hasattr(self,'tree'):return
    chosen=self.tree.selection()[0] if self.tree.selection() else None
    needle=self.search_text.get().strip().lower()
    if needle==getattr(self,'search_placeholder','').lower():needle=''
    pf=self.provider_filter.get() if hasattr(self,'provider_filter') else 'All providers'
    sf=self.status_filter.get() if hasattr(self,'status_filter') else 'All statuses'
    self.tree.delete(*self.tree.get_children())
    indexed={item['name']:idx for idx,item in enumerate(self.items)}
    groups=package_groups(self.items)
    col,reverse=self.table_sort
    def sortkey(group):
        item=group[1][0]
        return (group[0] if col=='title' else item.get('version','') if col=='version' else self.provider_for(item) if col=='source' else self.addon_status(item)).casefold()
    for group,items in sorted(groups.items(),key=sortkey,reverse=reverse):
        visible=[item for item in items if not needle or needle in (' '.join([group,item['name'],item['title'],item['version'],self.provider_for(item),self.addon_status(item)])).lower()]
        if not visible:continue
        providers={self.provider_for(item) for item in items}
        group_provider=next(iter(providers)) if len(providers)==1 else 'Mixed sources'
        group_status=package_status([self.addon_status(item) for item in items])
        if pf!='All providers' and pf!=group_provider and not any(self.provider_for(item)==pf for item in visible):continue
        if sf!='All statuses' and status_category(group_status)!=sf and not any(status_category(self.addon_status(item))==sf for item in visible):continue
        if len(items)==1:
            item=items[0];idx=indexed[item['name']]
            values=(item['title'],item['version'],self.latest_display(item),interface_summary(item['interface']),self.provider_for(item),self.visible_update_status(item),'Update' if self.can_install_update(item) else '—')
            self.tree.insert('','end',iid=str(idx),text='',values=values)
        else:
            key='pkg:'+group
            statuses=[self.addon_status(item) for item in items]
            providers=set(self.provider_for(item) for item in items)
            provider=next(iter(providers)) if len(providers)==1 else 'Mixed sources'
            versions=[i['version'] for i in items if i['version']!='Unknown']
            self.tree.insert('','end',iid=key,text='',values=(f'{group}  ({len(items)} folders)',versions[0] if versions else 'Unknown',self.latest_display(next((i for i in items if self.results.get(i['name'],{}).get('status')=='Update available'),items[0])),'—',provider,('Ready to update' if any(self.can_install_update(i) for i in items) else 'New version · manual' if any(self.results.get(i['name'],{}).get('status')=='Update available' for i in items) else simple_status(package_status(statuses))),'Update' if any(self.can_install_update(i) for i in items) else '—'),open=bool(needle) or group not in self.collapsed_groups)
            for item in visible:
                idx=indexed[item['name']]
                self.tree.insert(key,'end',iid=str(idx),text='↳ module',values=(item['title'],item['version'],self.latest_display(item),interface_summary(item['interface']),self.provider_for(item),self.visible_update_status(item),'Update' if self.can_install_update(item) else '—'))
    self.tree.tag_configure('available',foreground='#50d6a0')
    if chosen and self.tree.exists(chosen):self.tree.selection_set(chosen)

 def open_selected_provider(self):
    item=self.selected()
    if not item:return
    url=curseforge_url(item)
    if url:webbrowser.open(url);return
    repo=self.cfg.get('sources',{}).get(item['name'],'')
    if repo==RARE_SOURCE:self.open_rarescanner()
    elif repo:webbrowser.open('https://github.com/'+repo)
    else:messagebox.showinfo(APP,'No verified provider URL was found in this addon metadata.')

 def show_selected_details(self):
    item=self.selected()
    if not item:return
    project=item.get('curse_project_id') or 'Not provided'
    repo=self.cfg.get('sources',{}).get(item['name']) or 'Not linked'
    note=self.compatibility_note(item)
    messagebox.showinfo(APP,f"{item['title']}\n\nFolder: {item['name']}\nInstalled version: {item['version']}\nInterface: {item['interface'] or 'Unknown'}\nProvider: {self.provider_for(item)}\nCurseForge project ID: {project}\nGitHub source: {repo}\nStatus: {self.addon_status(item)}"+(('\n\n'+note) if note else ''))

 def toggle_group(self,group):
    if group in self.collapsed_groups:self.collapsed_groups.remove(group)
    else:self.collapsed_groups.add(group)
    self.render_addon_list()

 def compatibility_note(self,item):
    raw=str(item.get('interface',''))
    values=[int(x) for x in re.findall(r'\b\d{5,6}\b',raw)]
    if not values:return 'Compatibility unknown: this addon does not declare a numeric interface version.'
    if 16001 not in values:
        return 'Compatibility not confirmed: addon metadata does not list WoW Forever interface 16001. This is not proof the addon is broken.'
    return ''

 def render_update_groups(self):
    if not hasattr(self,'update_list'):return
    for child in self.update_list.winfo_children():child.destroy()
    buckets={'Updates available':[],'Verified up to date':[],'Unable to verify':[],'Not checked':[]}
    for group,items in package_groups(self.items).items():
        status=package_status([self.addon_status(i) for i in items])
        bucket=status_category(status)
        buckets[bucket].append((group,items,status))
    count=len(buckets['Updates available'])
    if hasattr(self,'update_count_badge'):
        self.update_count_badge.set(f'{count} packages with updates')
        self.install_updates_button.configure(state='normal' if count and not self.busy else 'disabled')
    for title,entries in buckets.items():
        tk.Label(self.update_list,text=f'{title.upper()}  ·  {len(entries)} packages',bg=self.bg,fg=self.green if title=='Updates available' else self.fg,font=('Segoe UI',11,'bold'),anchor='w').pack(fill='x',pady=(13,7))
        if not entries:tk.Label(self.update_list,text='None',bg=self.bg,fg=self.muted,anchor='w').pack(fill='x',pady=(0,5))
        for group,items,status in entries:
            line=tk.Frame(self.update_list,bg=self.panel,padx=12,pady=9,highlightbackground=self.edge,highlightthickness=1)
            line.pack(fill='x',pady=2)
            caption=group+(f'  ·  {len(items)} folders' if len(items)>1 else '  ·  v'+items[0]['version'])
            tk.Label(line,text=caption,bg=self.panel,fg=self.fg,font=('Segoe UI',10,'bold'),anchor='w').pack(side='left')
            tk.Label(line,text=status,bg=self.panel,fg=self.green if status in ('Up to date','Update available') else self.muted,font=('Segoe UI',9)).pack(side='right')
            if len(items)>1:
                tk.Label(self.update_list,text='    '+', '.join(i['name'] for i in items),bg=self.bg,fg=self.muted,wraplength=920,justify='left',anchor='w',font=('Segoe UI',9)).pack(fill='x',pady=(1,5))
    self.update_canvas.configure(scrollregion=self.update_canvas.bbox('all'))

 def toggle_addon(self,name,idx):
    self.expanded_addon=None if self.expanded_addon==name else name
    self.tree.selection_set(str(idx))
    self.render_addon_list()

 def render_history(self):
    if not hasattr(self,'history_list'):return
    self.history_list.delete(0,'end')
    records=read_history()
    if not records:self.history_list.insert('end','No recorded activity yet. Future installs and updates will appear here.')
    for rec in records:
        self.history_list.insert('end',f"{rec.get('date','')}  |  {rec.get('event','')}  |  {rec.get('addons','')}  {rec.get('detail','')[:90]}")

 def render_cards(self):
    for child in self.addon_cards.winfo_children():child.destroy()
    # Dashboard is a preview, not an unbounded list.
    preview=[]
    groups={}
    for item in self.items:groups.setdefault(addon_group(item),[]).append(item)
    for group in ('Questie + QuestieDB','Bagnon family','Other addons'):
        preview.extend(groups.get(group,[])[:2])
    preview=preview[:5]
    for item in preview:
        card=tk.Frame(self.addon_cards,bg=self.panel,padx=15,pady=11,highlightbackground=self.edge,highlightthickness=1)
        card.pack(fill='x',pady=4)
        row=tk.Frame(card,bg=self.panel);row.pack(fill='x')
        tk.Label(row,text=(item['name'] if item['name']=='Questie' else item['title']),bg=self.panel,fg=self.fg,font=('Segoe UI',11,'bold'),anchor='w').pack(side='left')
        tk.Label(row,text='v'+item['version'],bg=self.panel,fg=self.muted,font=('Segoe UI',10)).pack(side='right')
        status=self.addon_status(item)
        tk.Label(card,text=status,bg=self.panel,fg=self.green if status=='Up to date' else self.muted,font=('Segoe UI',9),anchor='w').pack(fill='x',pady=(4,0))
    self.dashboard_more.set(f'Showing {len(preview)} of {len(self.items)} addons across related groups. View all addons for the complete list.' if len(self.items)>len(preview) else 'All installed addons shown.')
    if hasattr(self,'library_hint'):
        count=len(package_groups(self.items))
        updates=len({addon_group(i) for i in self.items if self.results.get(i['name'],{}).get('status')=='Update available'})
        self.library_hint.set(f'{count} installed packages' + (f'  ·  {updates} with updates available' if updates else '  ·  Right-click an addon for details'))
    self.installed_text.set(str(len(package_groups(self.items))))
    self.updates_text.set(str(len({addon_group(i) for i in self.items if self.results.get(i['name'],{}).get('status')=='Update available'})))
    self.render_addon_list()
    self.render_update_groups()

 def open_rarescanner(self):
    webbrowser.open(RARE_URL)
    self.status.set('Official RareScanner Forever files opened in browser. Download the Forever ZIP, then drag it into the app. Never choose Retail.')

 def autolink(self):
    linked=[]
    for item in self.items:
        if item['name'] in ('Questie','QuestieDB'):
            self.cfg.setdefault('sources',{})[item['name']]='Questie/Questie'
            linked.append(item['name'])
        elif item['name']=='RareScanner':
            self.cfg.setdefault('sources',{})[item['name']]=RARE_SOURCE
            linked.append(item['name'])
        elif item['name']!='HinoCompanion':
            repo=source_from_metadata(item)
            if repo and not self.cfg.setdefault('sources',{}).get(item['name']):
                self.cfg['sources'][item['name']]=repo
                linked.append(item['name'])
    save_config(self.cfg);self.refresh()
    self.status.set(f"Linked {len(linked)} addon folders; identified {sum(bool(i.get('curse_project_id')) for i in self.items)} CurseForge project IDs. CurseForge downloads remain manual.")

 def export_source_report(self):
    """Export source evidence and coverage without exposing local credentials."""
    if not self.items:
        messagebox.showinfo(APP,'Scan the addon folder first.');return
    dest=filedialog.asksaveasfilename(title='Export addon source report',defaultextension='.json',filetypes=[('JSON files','*.json')],initialfile='hino-addon-sources.json')
    if not dest:return
    records=[]
    for item in self.items:
        identity=item.get('source_identity') or identify_source(item)
        repo=self.cfg.get('sources',{}).get(item['name'],'')
        result=self.results.get(item['name'],{})
        records.append({'folder':item['name'],'title':item.get('title'),'installed_version':item.get('version'),
            'interface':item.get('interface'),'toc_files':item.get('toc_files',[]),
            'declared_dependencies':item.get('dependencies',[]),'part_of':item.get('part_of',''),
            'source_provider':identity.get('provider'),'source_id':identity.get('project_id'),
            'source_evidence':identity.get('evidence'),'github_repo_linked':repo or None,
            'online_status':result.get('status','Not checked online')})
    try:
        Path(dest).write_text(json.dumps({'schema':1,'application_version':'3.5.0',
            'note':'Identified project metadata is not proof of update compatibility or download permission.',
            'addon_folders':records},indent=2),encoding='utf-8')
        self.status.set(f'Exported source evidence for {len(records)} addon folders.')
    except OSError as exc:messagebox.showerror(APP,'Could not export report: '+str(exc))

 def test_connection(self):
    if self.busy:return
    self.status.set('Testing secure connection to GitHub...')
    def done(result,error):
        self.busy=False
        if error:
            self.status.set('GitHub connection FAILED: '+error)
            messagebox.showerror(APP,'Secure GitHub connection failed:\n\n'+error)
        else:
            self.status.set(result)
            messagebox.showinfo(APP,result)
    self.task(test_github_connection,done)

 def check_all(self):
    if self.busy:return
    for item in self.items:
        if item['name'] in ('Questie','QuestieDB'):
            self.cfg.setdefault('sources',{})[item['name']]='Questie/Questie'
        elif item['name']=='RareScanner':
            self.cfg.setdefault('sources',{})[item['name']]=RARE_SOURCE
        elif item['name']!='HinoCompanion' and not self.cfg.setdefault('sources',{}).get(item['name']):
            repo=source_from_metadata(item)
            if repo:self.cfg['sources'][item['name']]=repo
    save_config(self.cfg)
    repos=sorted(set(self.cfg.get('sources',{}).get(x['name'],'') for x in self.items)-{''})
    projects={cf_project_for(i) for i in self.items}
    projects.discard(None)
    api_key=self.cf_key.get().strip() if hasattr(self,'cf_key') else ''
    self.status.set(f'Checking {len(repos)} GitHub source(s), {len(projects) if api_key else 0} CurseForge project(s)...')
    def work():
        output={'github':{},'curseforge':{}}
        for repo in repos:
            try:output['github'][repo]=latest(repo)
            except Exception as e:output['github'][repo]={'error':str(e)}
        if api_key:
            for project in sorted(projects):
                try:output['curseforge'][project]={'files':cf_files(api_key,project)}
                except Exception as e:output['curseforge'][project]={'error':str(e)}
        return output
    def done(output,error):
        self.busy=False
        if error:self.status.set('Update check failed: '+error);return
        self.results={}
        github=output['github'];curseforge=output['curseforge']
        for item in self.items:
            repo=self.cfg.get('sources',{}).get(item['name'],'')
            if not repo:continue
            release=github.get(repo,{})
            if 'error' in release:
                self.results[item['name']]={'status':'Check failed','reason':release['error']}
            else:
                status,asset=classify(item,release)
                self.results[item['name']]={'release':release,'asset':asset,'status':status}
        for item in self.items:
            project=cf_project_for(item)
            if not project or not api_key:continue
            result=curseforge.get(project,{})
            if 'error' in result:
                self.results[item['name']]={'status':'Check failed','reason':result['error'],'cf_metadata_only':True}
                continue
            files=result.get('files',[])
            # For package families with one verified project identity, compare the core
            # addon version only; don't present module versions as separate releases.
            family=package_groups(self.items).get(addon_group(item),[])
            leader=next((m for m in family if m['name']==addon_group(item) or m['name']=='Polestar'),family[0])
            status,file=cf_release_status(leader.get('version',''),files)
            self.results[item['name']]={'status':status,'cf_metadata_only':True,
                'latest_cf_file':file,'project_id':project,
                'reason':('Forever-labelled CurseForge metadata only; no automatic download' if file else 'No verifiable compatible version in returned files')}
        failed=[f'GitHub {p}: {v["error"]}' for p,v in github.items() if 'error' in v]
        failed += [f'CurseForge {p}: {v["error"]}' for p,v in curseforge.items() if 'error' in v]
        packages=package_groups(self.items)
        updates=sum(1 for members in packages.values() if package_status([self.results.get(i['name'],{}).get('status','Not checked') for i in members])=='Update available')
        self.overview.set(f'{len(packages)} packages / {len(self.items)} addon folders  •  {updates} update(s) identified')
        self.update_detail.set(f'{len(repos)} GitHub sources checked; {len(curseforge)} CurseForge projects queried. CurseForge is metadata-only; other sources may be unverified.')
        self.render_cards()
        installable=sum(1 for members in packages.values() if any(self.can_install_update(i) for i in members))
        self.status.set(f'Checked {len(repos)} GitHub source(s) and {len(curseforge)} CurseForge project(s). {updates} package(s) have newer versions; {installable} can update automatically. '+(f'{len(failed)} source check(s) failed.' if failed else 'No lookup failures.'))
        if failed:messagebox.showwarning(APP,'Some sources could not be verified:\n\n'+'\n'.join(failed[:12]))
    self.task(work,done)

 def cancel_download(self):
    if self.update_in_progress:
        self.cancel_event.set()
        self.progress_label.set('Cancelling...')
        self.status.set('Cancellation requested. Finishing current small read; installation will not start if cancelled.')

 def report_progress(self,label,done,total):
    def ui():
        if not self.update_in_progress:return
        mb=done/(1024*1024)
        if total:
            pct=min(100,int(done*100/total))
            self.progress.configure(value=pct)
            self.progress_label.set(f'{label}: {pct}% ({mb:.1f} MB)')
        else:
            self.progress.configure(value=0)
            self.progress_label.set(f'{label}: {mb:.1f} MB downloaded')
    try:self.root.after(0,ui)
    except RuntimeError:pass

 def report_stage(self,label,done,total):
    def ui():
        if not self.update_in_progress:return
        pct=min(100,int(done*100/total)) if total else 0
        self.progress.configure(value=pct)
        self.progress_label.set(f'{label}: {pct}%')
        self.status.set(label+' — installed addons are preserved until installation is prepared.')
    try:self.root.after(0,ui)
    except RuntimeError:pass

 def report_folder_scan(self,done,total):
    def ui():
        if not self.update_in_progress:return
        self.progress.configure(value=100 if total else 0)
        self.progress_label.set(f'Checking folders: {done} scanned' if not total else f'Found addon folders ({done} scanned)')
    try:self.root.after(0,ui)
    except RuntimeError:pass

 def update_all(self, only_names=None):
    if self.busy:return
    candidates=[x for x in self.items if self.results.get(x['name'],{}).get('status')=='Update available' and self.results.get(x['name'],{}).get('asset') and (only_names is None or x['name'] in only_names)]
    if not candidates:
        messagebox.showinfo(APP,'No verified automatic updates available. GitHub-based addons with a declared source can update automatically after compatibility checks. Some providers do not offer direct downloads.');return
    groups={}
    for x in candidates:
        repo=self.cfg['sources'].get(x['name'])
        groups.setdefault(repo,[]).append(x)
    desc='\n'.join(f'{repo}: '+', '.join(i['name'] for i in items) for repo,items in groups.items())
    if not messagebox.askyesno(APP,'Close WoW completely. Install these updates?\n\n'+desc+'\n\nRareScanner is updated separately using official CurseForge Forever ZIP files.\n\nBackups are created outside AddOns.'):return
    jobs=[]
    for repo,items in groups.items():
        result=self.results[items[0]['name']]
        jobs.append((repo,result['release'],result['asset'],[i['name'] for i in items]))
    wow_root=resolve_wow(self.path.get())/'Interface'/'AddOns'
    self.cancel_event.clear();self.update_in_progress=True
    self.cancel_button.configure(state='normal');self.progress.configure(value=0)
    self.progress_label.set('Connecting...');self.status.set('Downloading updates; installed addons are unchanged until all downloads pass validation.')
    def work():
        # Stage each bundle exactly once. Never extract the same archive twice.
        with tempfile.TemporaryDirectory(prefix='hino-staged-updates-') as td:
            extracted=[]
            for i,(repo,rel,asset,names) in enumerate(jobs):
                check_cancel(self.cancel_event)
                z=Path(td)/f'bundle-{i}.zip'
                self.report_stage('Downloading '+repo,0,100)
                download_asset(asset,z,progress=lambda n,t,label=repo:self.report_progress(label,n,t),cancelled=self.cancel_event,max_seconds=150)
                check_cancel(self.cancel_event)
                unpack=Path(td)/f'unpack-{i}';unpack.mkdir()
                self.report_stage('Extracting '+repo,0,100)
                safe_extract_zip(z,unpack,cancelled=self.cancel_event,
                    progress=lambda n,t,label=repo:self.report_stage('Extracting '+label,n,t))
                self.report_stage('Checking addon folders',0,100)
                folders=addon_folders(unpack,cancelled=self.cancel_event,
                    progress=lambda n,t:self.report_folder_scan(n,t))
                found={f.name for f in folders}
                if not set(names).issubset(found):
                    raise ValueError('Package missing expected addons: '+', '.join(set(names)-found))
                if repo not in ('Questie/Questie',RARE_SOURCE):
                    # Never let a third-party package install extra addon folders.
                    if found!=set(names):
                        raise ValueError('Update package folder mismatch. Expected: '+', '.join(names)+'; found: '+', '.join(sorted(found)))
                    for folder in folders:
                        original=next((item for item in self.items if item['name']==folder.name),None)
                        info=toc_info(folder)
                        if not original or not info or not compatible_interfaces(original.get('interface',''),info.get('interface','')):
                            raise ValueError('Update is not verified for this WoW client: '+folder.name+' (interface mismatch)')
                        if version_tuple(info.get('version',''))<=version_tuple(original.get('version','')):
                            raise ValueError('ZIP does not contain a newer addon version: '+folder.name)
                if repo==RARE_SOURCE and found!={'RareScanner'}:
                    raise ValueError('Unexpected RareScanner package folders: '+', '.join(sorted(found)))
                if repo=='Questie/Questie' and found!={'Questie','QuestieDB'}:
                    raise ValueError('Unexpected Questie bundle folders: '+', '.join(sorted(found)))
                extracted.append((repo,rel,folders))
            check_cancel(self.cancel_event)
            outcomes=[]
            for repo,rel,folders in extracted:
                self.report_stage('Preparing installation '+repo,0,100)
                result=install_staged(folders,wow_root,cancelled=self.cancel_event,
                    progress=lambda n,t,label=repo:self.report_stage('Preparing '+label,n,t))
                outcomes.append((repo,rel['tag'],result))
            return outcomes
    def done(out,err):
        self.busy=False;self.update_in_progress=False;self.expanded_addon=None;self.collapsed_groups={'Bagnon family','GearQuest Forever','Questie + QuestieDB','Polestar Guides'};self.backup_paths=[]
        self.cancel_button.configure(state='disabled')
        if err:
            self.progress_label.set('Cancelled' if 'cancel' in err.lower() else 'Failed')
            self.progress.configure(value=0)
            self.status.set('Update stopped: '+err+'. Check addon versions before retrying.')
            write_history('Update stopped',', '.join(x['name'] for x in candidates),err)
            if 'cancel' not in err.lower():messagebox.showerror(APP,'Update stopped:\n'+err)
            return
        self.progress.configure(value=100);self.progress_label.set('Installation complete')
        for repo,tag,_ in out:
            for x in self.items:
                if self.cfg['sources'].get(x['name'])==repo:self.cfg.setdefault('installed_tags',{})[x['name']]=tag
        save_config(self.cfg)
        for repo,tag,res in out:write_history('Automatic update',', '.join(res[0]),f'{tag} · backup {res[1]}')
        self.refresh()
        self.status.set('Updates installed successfully. Scan completed.')
        messagebox.showinfo(APP,'Updates installed.\n\n'+'\n'.join(f'{r}: {tag} | Backup: {res[1]}' for r,tag,res in out))
    self.task(work,done)

 def restore_backup(self):
    root=resolve_wow(self.path.get())/'Interface'/'AddOns'
    backups=backup_base(root)
    try:migrate_legacy_backups(root)
    except OSError as e:
        messagebox.showwarning(APP,'Could not move old backups: '+str(e))
    if not backups.is_dir():messagebox.showinfo(APP,'No backups found.');return
    choice=str(self.backup_paths[self.backup_list.curselection()[0]]) if self.backup_list.curselection() and self.backup_paths else filedialog.askdirectory(initialdir=str(backups),title='Choose a Hino backup folder')
    if not choice:return
    chosen=Path(choice).resolve()
    if backups.resolve() not in chosen.parents or not chosen.is_dir():messagebox.showerror(APP,'Select a folder inside HinoAddonManager/Backups.');return
    folders=[f for f in chosen.iterdir() if f.is_dir() and toc_info(f)]
    if not folders:messagebox.showerror(APP,'No addon folders in selected backup.');return
    if not messagebox.askyesno(APP,'Close WoW first. Restore '+', '.join(f.name for f in folders)+'? Current versions will be backed up again.'):return
    try:
        with tempfile.TemporaryDirectory() as td:
            archive=Path(td)/'restore.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for f in folders:
                    for child in f.rglob('*'):
                        if child.is_file():z.write(child,child.relative_to(chosen))
            result=install_zip(archive,root)
        write_history('Backup restored',', '.join(result[0]),str(chosen))
        self.refresh();messagebox.showinfo(APP,'Restored: '+', '.join(result[0])+'\nPrevious versions backed up to '+result[1])
    except Exception as e:messagebox.showerror(APP,str(e))
 def browse(self):
    d=filedialog.askdirectory(initialdir=self.path.get());
    if d:self.path.set(d);self.refresh()
 def selected(self):
    sel=self.tree.selection()
    if not sel:messagebox.showinfo(APP,'Select an addon first.');return None
    key=sel[0]
    if key.startswith('pkg:'):
        group=key[4:]
        names=package_groups(self.items).get(group,[])
        if not names:return None
        messagebox.showinfo(APP,f'{group} contains {len(names)} addon folders. Expand the package and select a specific module for this action.')
        return None
    return self.items[int(key)]
 def refresh(self):
    try:
        migrate_legacy_backups(resolve_wow(self.path.get())/'Interface'/'AddOns')
    except OSError:
        pass  # A locked legacy backup can still be restored after moving it manually.
    self.cfg['wow']=str(resolve_wow(self.path.get()));self.path.set(self.cfg['wow'])
    self.cfg.setdefault('sources',{})['RareScanner']=RARE_SOURCE
    try:self.items=scan(self.path.get())
    except Exception as e:self.status.set(str(e));return
    for item in self.items:
        if item['name'] in ('Questie','QuestieDB'):
            self.cfg.setdefault('sources',{})[item['name']]='Questie/Questie'
        elif item['name'] not in ('RareScanner','HinoCompanion') and not self.cfg.setdefault('sources',{}).get(item['name']):
            repo=source_from_metadata(item)
            if repo:self.cfg['sources'][item['name']]=repo
    save_config(self.cfg)
    self.tree.delete(*self.tree.get_children())
    for i,item in enumerate(self.items):
        repo=self.cfg.get('sources',{}).get(item['name'],'')
    self.overview.set(f'{len(package_groups(self.items))} packages / {len(self.items)} addon folders installed')
    self.results={}
    self.render_cards()
    self._backup_loaded=False
    if not self._backup_loading:self.refresh_backups()
    self.status.set(f"{len(self.items)} addon folders detected; {sum(bool(i.get('curse_project_id')) for i in self.items)} have CurseForge project IDs. Automatic installs require verified download access.")
 def set_source(self):
    item=self.selected()
    if not item:return
    if item['name']=='RareScanner':
        messagebox.showinfo(APP,'RareScanner uses the official CurseForge Forever listing. Use the RareScanner Forever releases button.');return
    prev=self.cfg.get('sources',{}).get(item['name'],'')
    value=simpledialog.askstring('Link GitHub source',f'GitHub repository for {item["name"]}:\n(e.g. owner/repo)\n\nLeave empty to unlink.',initialvalue=prev,parent=self.root)
    if value is None:return
    try:repo=parse_repo(value) if value.strip() else ''
    except Exception as e:messagebox.showerror(APP,str(e));return
    if repo:self.cfg.setdefault('sources',{})[item['name']]=repo
    else:self.cfg.setdefault('sources',{}).pop(item['name'],None)
    save_config(self.cfg);self.refresh()
 def task(self,work,done):
    if self.busy:return
    self.busy=True
    def runner():
        try:r=work();self.root.after(0,lambda:done(r,None))
        except Exception as e:
            error=f'{type(e).__name__}: {e}'
            self.root.after(0,lambda error=error:done(None,error))
    threading.Thread(target=runner,daemon=True).start()
 def check(self):
    item=self.selected()
    if not item:return
    repo=self.cfg.get('sources',{}).get(item['name'])
    if not repo:messagebox.showinfo(APP,'Link a source first.');return
    if item['name']=='RareScanner':
        self.open_rarescanner();return
    self.status.set('Checking '+repo+' ...')
    def done(result,error):
        self.busy=False
        if error:
            self.status.set('Check failed: '+error)
            messagebox.showerror(APP,'Update check failed:\n\n'+error)
            return
        tag=result['tag'];self.cfg.setdefault('latest',{})[item['name']]=result;save_config(self.cfg)
        installed=self.cfg.get('installed_tags',{}).get(item['name'])
        note='Installed by Hino Manager' if installed else 'Installed version not verified against release tag'
        self.status.set(f'{item["name"]}: GitHub latest {tag}; local TOC version {item["version"]}. {note}. {len(result["assets"])} ZIP assets. Review before updating.')
        idx=next((i for i,v in enumerate(self.items) if v['name']==item['name']),None)
        if idx is not None and self.tree.exists(str(idx)):self.tree.set(str(idx),'status','Latest: '+tag)
    self.task(lambda:latest(repo),done)
 def update(self):
    item=self.selected()
    if not item:return
    if item['name']=='RareScanner':self.open_rarescanner();return
    if self.results.get(item['name'],{}).get('status')!='Update available' or self.results.get(item['name'],{}).get('cf_metadata_only'):
        messagebox.showinfo(APP,'No verified update is ready for this addon. Run Check Updates first. CurseForge identification alone does not authorise automatic downloads.')
        return
    if item['name'] in ('Questie','QuestieDB'):
        self.update_all({'Questie','QuestieDB'})
    else:self.update_all({item['name']})

 def handle_drop(self,event):
    paths=[Path(x) for x in self.root.tk.splitlist(event.data)]
    self.install_files(paths)

 def install_files(self,paths):
    if self.busy:return
    paths=[p for p in paths if p.is_file() and p.suffix.lower()=='.zip']
    if not paths:
        messagebox.showerror(APP,'Drop one or more downloaded .zip addon files.');return
    if not messagebox.askyesno(APP,'Close WoW completely before installing.\n\nInstall '+str(len(paths))+' ZIP(s)? Existing addon folders will be backed up.'):
        return
    root=resolve_wow(self.path.get())/'Interface'/'AddOns'
    self.status.set('Installing '+str(len(paths))+' addon ZIP(s) ...')
    def work():
        out=[]
        for path in paths:
            try:out.append((path.name,install_zip(path,root),None))
            except Exception as e:out.append((path.name,None,str(e)))
        return out
    def done(out,error):
        self.busy=False
        if error:messagebox.showerror(APP,error);return
        for name,result,install_error in out:
            write_history('ZIP installed' if result else 'ZIP failed',', '.join(result[0]) if result else name,str(result[1]) if result else install_error)
        self.refresh()
        lines=[name+': '+('Installed '+', '.join(result[0]) if result else 'FAILED: '+err) for name,result,err in out]
        self.status.set(' | '.join(lines)[:800])
        messagebox.showinfo(APP,'Addon installation results:\n\n'+'\n'.join(lines))
    self.task(work,done)

 def local_zip(self):
    f=filedialog.askopenfilename(filetypes=[('ZIP archives','*.zip')]);
    if not f:return
    self.install_files([Path(f)])
 def open_folder(self):
    p=resolve_wow(self.path.get())/'Interface'/'AddOns'
    if p.is_dir():os.startfile(p) if hasattr(os,'startfile') else None
    else:messagebox.showerror(APP,'Folder not found: '+str(p))

if __name__=='__main__':
    root=TkinterDnD.Tk() if TkinterDnD else tk.Tk();GUI(root);root.mainloop()
