"""Cache original collection images so baked-in catalog labels are not duplicated."""
import hashlib
import io
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import urllib.request
from PIL import Image

CACHE = Path.home()/'.cache/met-screensaver/originals'
USER_AGENT='PompeiiWeeklyExhibit/2.0 (personal educational display; open museum collections and licensed Commons images)'
_request_lock=threading.Lock()
_next_request=0.0


def urls(record):
    metadata=record.get('metadata',{})
    return list(dict.fromkeys(u for u in (metadata.get('image_url'),metadata.get('image_url_small'))
                             if isinstance(u,str) and u.startswith(('https://','http://'))))


def cache_path(record):
    candidates=urls(record)
    if not candidates: return None
    key=hashlib.sha256(candidates[0].encode()).hexdigest()
    return CACHE/(key+'.img')


def cached(record):
    path=cache_path(record)
    return path if path and path.exists() else None


def fetch(record):
    global _next_request
    target=cache_path(record)
    if target is None: return None
    if target.exists(): return target
    CACHE.mkdir(parents=True,exist_ok=True)
    for url in urls(record):
        for attempt in range(2):
            temporary=None
            try:
                with _request_lock:
                    time.sleep(max(0,_next_request-time.monotonic()))
                    _next_request=time.monotonic()+0.27
                headers={'User-Agent':USER_AGENT}
                if 'artic.edu' in url: headers['AIC-User-Agent']=USER_AGENT
                with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as response:
                    data=response.read(40*1024*1024+1)
                if len(data)>40*1024*1024: raise ValueError('Image too large')
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                with tempfile.NamedTemporaryFile(dir=CACHE,prefix='.download-',delete=False) as handle:
                    temporary=Path(handle.name)
                    handle.write(data)
                os.replace(temporary,target)
                return target
            except Exception:
                if attempt==0: time.sleep(1)
            finally:
                if temporary: temporary.unlink(missing_ok=True)
    return None


class BackgroundCache:
    def __init__(self, on_ready):
        self.on_ready=on_ready
        self.jobs=queue.Queue()
        self.pending=set()
        for _ in range(2):
            threading.Thread(target=self.worker,daemon=True).start()

    def request(self, record):
        path=cache_path(record)
        if path and path not in self.pending and not path.exists():
            self.pending.add(path)
            self.jobs.put(record)

    def worker(self):
        while True:
            record=self.jobs.get()
            try:
                path=fetch(record)
                if path: self.on_ready(record,path)
            finally:
                self.jobs.task_done()
