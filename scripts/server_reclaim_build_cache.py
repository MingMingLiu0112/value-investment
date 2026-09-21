"""Remove only inspected, unused, untagged builds of this exact project."""
import json
import subprocess
import sys

KEEP = ('11b32bff57f0','73dde45911ea','317b0d568fc1')
OBSERVED = ('d9cdee406885','e49a3d1884b7','f39049e2890e','58644a5fbb41',
    '9b11cd96700a','899638d33879','91456cba487d','e2a0111dc2b0','3d1a305cc6be',
    '06a06b1101db','963ad162d049','5753a185496f','57e457385b05','8faff6481c3d',
    'b31ec74c20c5','7620b3de4445','d1fcadaced5a','d81321c26dcb','305397cbe86b',
    '8def1756f302','9553e9d7a460','ce62df587ac3','a7aa21c06901','1ecf67de2b35',
    '0f2cd7765b6e','1fa77b16d3aa','753eefe5057c','89b1e1e3139d')

for image_id in OBSERVED:
    raw=subprocess.run(['podman','image','inspect',image_id],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    if raw.returncode: continue
    meta=json.loads(raw.stdout)[0]
    if meta.get('RepoTags') or any(meta['Id'].startswith(i) for i in KEEP): continue
    used=subprocess.check_output(['podman','ps','-a','--filter',f'ancestor={image_id}','--format','{{.ID}}'],universal_newlines=True).strip()
    if used: continue
    # Read project metadata in a read-only, networkless container. No host mounts
    # and no application entrypoint; an unrelated image will fail this check.
    check=subprocess.run(['podman','run','--rm','--network','none','--memory=64m','--read-only',
        '--entrypoint','/bin/sh',image_id,'-c',
        'test -f /app/pyproject.toml && grep -q \'name = "value-investment-agent"\' /app/pyproject.toml'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    if check.returncode: continue
    print(json.dumps({'confirmed_unused_project_image':image_id}),flush=True)
    if '--apply' in sys.argv:
        result=subprocess.run(['podman','rmi',image_id],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
        print(json.dumps({'image':image_id,'removed':result.returncode==0}),flush=True)
