"""TEST_ONLY cache tests; no financial fact is mocked into real acceptance."""
from hashlib import sha256
import json
import os
from value_investment_agent.infrastructure.screening.verified_screen_cache_v1 import VerifiedScreenCache
import pytest


def bound(root,name,payload):
 p=root/'runtime'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload),encoding='utf-8')
 return dict(path=p.relative_to(root).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())


def test_cache_retains_sibling_receipt_and_checks_bytes_even_same_mtime(tmp_path):
 raw=bound(tmp_path,'raw.json',{'amount':1});receipt=bound(tmp_path,'acquisition.json',raw)
 manifest=bound(tmp_path,'manifest.json',dict(input=dict(raw,receipt=receipt)))
 c=VerifiedScreenCache();result={'TEST_ONLY':'result'};c.put(tmp_path,manifest,result)
 before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (tmp_path/'runtime').rglob('*.json')}
 assert c.get(tmp_path,manifest)==result
 assert before=={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in before}
 p=tmp_path/raw['path'];stamp=p.stat();p.write_bytes(p.read_bytes().replace(b'1',b'2'));os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
 with pytest.raises(ValueError,match='HASH_CHANGED'):c.get(tmp_path,manifest)


def test_result_and_sibling_receipt_tampering_cannot_use_cache(tmp_path):
 source=bound(tmp_path,'raw.json',{'value':1});receipt=bound(tmp_path,'acquisition.json',source)
 result=bound(tmp_path,'screening.json',{'TEST_ONLY':'output'})
 manifest=bound(tmp_path,'manifest.json',dict(source=dict(source,receipt=receipt),result=result))
 c=VerifiedScreenCache();c.put(tmp_path,manifest,{'TEST_ONLY':'verified'})
 (tmp_path/receipt['path']).write_text('{}')
 with pytest.raises(ValueError,match='HASH_CHANGED'):c.get(tmp_path,manifest)


def test_one_entry_and_version_changes_force_cold_replay(tmp_path):
 a=bound(tmp_path,'a.json',{});b=bound(tmp_path,'b.json',{})
 c=VerifiedScreenCache();c.put(tmp_path,a,{'a':1});assert c.get(tmp_path,b) is None
 c.put(tmp_path,b,{'b':1});assert c.get(tmp_path,a) is None


def test_path_escape_and_conflicting_hash_rejected(tmp_path):
 c=VerifiedScreenCache()
 with pytest.raises(ValueError,match='OUTSIDE_RUNTIME'):c.put(tmp_path,dict(path='../secret',sha256='a'*64),{})
 a=bound(tmp_path,'a.json',{});bad=dict(a,sha256='b'*64);m=bound(tmp_path,'manifest.json',[a,bad])
 with pytest.raises(ValueError,match='CONFLICTING_BINDINGS'):c.put(tmp_path,m,{})


def test_cache_budget_is_bounded_per_reader_not_a_native_source_admission(tmp_path):
    from value_investment_agent.infrastructure.screening.verified_screen_cache_v1 import VerifiedScreenCache
    from hashlib import sha256
    import pytest
    path=tmp_path/'runtime'/'TEST_ONLY.bin';path.parent.mkdir();path.write_bytes(b'x'*120)
    binding=dict(path='runtime/TEST_ONLY.bin',sha256=sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError,match='CACHE_SOURCE_TOO_LARGE'):VerifiedScreenCache(max_file_bytes=100).put(tmp_path,binding,{})
    cache=VerifiedScreenCache(max_file_bytes=200);cache.put(tmp_path,binding,{'TEST_ONLY':True})
    assert cache.get(tmp_path,binding)=={'TEST_ONLY':True}
    for bad in [True,0,-1,192_000_001]:
        with pytest.raises(ValueError):VerifiedScreenCache(max_file_bytes=bad)
