"""Archive bounded official security-list responses for schema inspection."""
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path

from openpyxl import load_workbook
import requests


OUTPUT = Path('runtime/exchange-lists')
SSE_PARAMS = {
    'REG_PROVINCE':'', 'CSRC_CODE':'', 'STOCK_CODE':'',
    'sqlId':'COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L', 'COMPANY_STATUS':'2,4,5,7,8',
    'type':'inParams', 'isPagination':'true', 'pageHelp.cacheSize':'1',
    'pageHelp.beginPage':'1', 'pageHelp.pageSize':'10000', 'pageHelp.pageNo':'1', 'pageHelp.endPage':'1',
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    session.headers['User-Agent'] = 'Mozilla/5.0'
    jobs = [
        ('szse_a', 'GET', 'https://www.szse.cn/api/report/ShowReport',
         {'params':{'SHOWTYPE':'xlsx','CATALOGID':'1110','TABKEY':'tab1'}}),
        ('sse_main', 'GET', 'https://query.sse.com.cn/sseQuery/commonQuery.do',
         {'params':{**SSE_PARAMS,'STOCK_TYPE':'1'},'headers':{'Referer':'https://www.sse.com.cn/assortment/stock/list/share/'}}),
        ('sse_star', 'GET', 'https://query.sse.com.cn/sseQuery/commonQuery.do',
         {'params':{**SSE_PARAMS,'STOCK_TYPE':'8'},'headers':{'Referer':'https://www.sse.com.cn/assortment/stock/list/share/'}}),
        ('bse', 'POST', 'https://www.bse.cn/nqxxController/nqxxCnzq.do',
         {'data':{'page':'0','typejb':'T','xxfcbj[]':'2','xxzqdm':'','sortfield':'xxzqdm','sorttype':'asc'}}),
    ]
    for name, method, url, options in jobs:
        result = {'name':name,'fetched_at':datetime.now(timezone.utc).isoformat(),'url':url}
        try:
            response = session.request(method, url, timeout=(15,35), **options)
            response.raise_for_status()
            raw = response.content
            digest = hashlib.sha256(raw).hexdigest()
            extension = '.xlsx' if raw.startswith(b'PK') else '.txt'
            path = OUTPUT / (name + '-' + digest + extension)
            path.write_bytes(raw)
            result.update(sha256=digest,path=str(path),bytes=len(raw),url=response.url)
            if extension == '.xlsx':
                workbook = load_workbook(BytesIO(raw),read_only=True,data_only=True)
                workbook.active.reset_dimensions()
                rows = list(workbook.active.values)
                result.update(rows=len(rows)-1,sample=rows[:3])
                workbook.close()
            else:
                result['prefix'] = response.text[:1700]
        except Exception as error:
            result['error'] = f'{type(error).__name__}: {error}'
        (OUTPUT / (name + '-manifest.json')).write_text(json.dumps(result,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,default=str),flush=True)


if __name__ == '__main__':
    main()
