"""One verified public-screen read cache; every hit rehashes its immutable closure."""
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock


# Native loaders retain their own input limits. The verified closure includes
# the existing 98 MB financial export; this bound only limits cache rehash reads.
class VerifiedScreenCache:
    def __init__(self):
        self.lock=RLock()
        self._entry=None

    def get(self,root,binding):
        key=(str(Path(root).resolve()),binding['path'],binding['sha256'])
        if self._entry is None or self._entry[0]!=key:return None
        for name,digest in self._entry[1]:
            path=(Path(root)/name).resolve()
            if not path.is_relative_to((Path(root)/'runtime').resolve()):raise ValueError('CACHE_SOURCE_OUTSIDE_RUNTIME')
            if path.stat().st_size>128_000_000 or sha256(path.read_bytes()).hexdigest()!=digest:
                self._entry=None
                raise ValueError('CACHED_SCREEN_SOURCE_HASH_CHANGED')
        return self._entry[2]

    def put(self,root,binding,result):
        root=Path(root).resolve();seen={}
        def visit(value):
            if isinstance(value,dict):
                if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str) and len(value['sha256'])==64:
                    name=value['path'];target=(root/name).resolve()
                    if Path(name).is_absolute() or '..' in Path(name).parts or not target.is_relative_to(root/'runtime'):
                        raise ValueError('CACHE_SOURCE_OUTSIDE_RUNTIME')
                    if name in seen:
                        if seen[name]!=value['sha256']:raise ValueError('CACHE_CONFLICTING_BINDINGS')
                    else:
                        if target.stat().st_size>128_000_000:raise ValueError('CACHE_SOURCE_TOO_LARGE')
                        raw=target.read_bytes()
                        if sha256(raw).hexdigest()!=value['sha256']:raise ValueError('CACHE_CLOSURE_HASH_MISMATCH')
                        seen[name]=value['sha256'];url=value.get('source_url','')
                        native=('CompanyFinanceService.getFinanceReport2022' in url or 'datacenter-web.eastmoney.com/api/data/v1/get' in url)
                        if target.suffix=='.json' and target.name not in {'screening.json','receipt.json'} and not native:
                            visit(json.loads(raw))
                    # Receipts are siblings of path/hash, not children of response bytes.
                    for key,item in value.items():
                        if key not in {'path','sha256'}:visit(item)
                else:
                    for item in value.values():visit(item)
            elif isinstance(value,list):
                for item in value:visit(item)
        visit(binding)
        self._entry=((str(root),binding['path'],binding['sha256']),tuple(sorted(seen.items())),result)


SCREEN_CACHE=VerifiedScreenCache()
