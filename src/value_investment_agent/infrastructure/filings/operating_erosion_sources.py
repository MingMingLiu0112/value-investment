"""Retained official issuer layout adapter; no research/valuation/admission logic."""
from hashlib import sha256
from pathlib import Path
import re

from .pdf_text import extract_pages


PARSER_VERSION = 'operating-erosion-sources-v1'


def read_operating_erosion_sources(*, root: Path, symbol: str, sources: list, fields) -> dict:
    """Return bounded issuer specs and observed rounded percentages, not forecasts."""
    if symbol != '600519':
        raise ValueError('Unsupported operating erosion issuer/layout')
    root = root.resolve()
    catalog = {item['id']:item for item in sources}
    if len(catalog) != len(sources):
        raise ValueError('Duplicate operating source identities')
    declarations = [
        ('cninfo:1225114741', '2026-04-17', [61, 62], 6, ['FY2025', 'FY2024'], ['2025年度', '2024年度']),
        ('cninfo:1225475868', '2026-08-15', [30, 31], 5, ['H12026', 'H12025'], ['2026年半年度', '2025年半年度']),
    ]
    specs, bindings = [], []
    for source_id, published, pages, summary, periods, columns in declarations:
        item = catalog[source_id]
        url = 'https://static.cninfo.com.cn/finalpage/'+published+'/'+source_id.split(':')[1]+'.PDF'
        if (item['kind'] != 'official_issuer_filing'
                or item['issuer_identity']['security_code'] != symbol or item['location'] != url):
            raise ValueError('Operating source official issuer/URL identity differs')
        specs.append(dict(symbol=symbol, issuer='贵州茅台', source_id=source_id,
            path=item['local_path'], sha256=item['sha256'], source_url=url, published_date=published,
            original_acquired_at=None, statement_pages=pages, summary_page=summary,
            periods=periods, column_labels=columns, fields=sorted(fields)))
        bindings.append(dict(path=item['local_path'], sha256=item['sha256']))

    def check():
        for ref in bindings:
            path = (root/ref['path']).resolve()
            if (not path.is_relative_to(root) or path.relative_to(root).as_posix() != ref['path']
                    or sha256(path.read_bytes()).hexdigest() != ref['sha256']):
                raise ValueError('Operating source path/hash drift')
    check()
    page = extract_pages(root/specs[0]['path'], limit=10)[9]
    text = '\n'.join(line.strip() for line in page.splitlines() if line.strip())
    if ('贵州茅台酒股份有限公司2025年年度报告' not in re.sub(r'\s+', '', text)
            or '单位：元 币种：人民币' not in text
            or any(text.count(title) != 1 for title in (
                '主营业务分行业情况', '主营业务分产品情况', '产销量情况分析'))):
        raise ValueError('FY wine revenue/volume table boundaries unsupported')
    industry = text.split('主营业务分行业情况', 1)[1].split('主营业务分产品情况', 1)[0]
    volume = text.split('产销量情况分析', 1)[1].split('(3).', 1)[0]
    number = r'(-?\d[\d,]*(?:\.\d+)?)'
    revenue_rows = re.findall(r'^酒类\s+'+r'\s+'.join([number]*5)
        +r'\s+(?:减少|增加)\s+[\d.]+\s*个百', industry, re.M)
    volume_rows = re.findall(r'^酒类\s+吨\s+'+r'\s+'.join([number]*6)+r'\s*$', volume, re.M)
    if (len(revenue_rows) != 1 or len(volume_rows) != 1 or '营业收入比上' not in industry
            or '销售量比\n上年增减' not in volume):
        raise ValueError('FY mixed proxy row shape unsupported')
    check()
    return dict(symbol=symbol, parser_version=PARSER_VERSION, specs=specs, source_bindings=bindings,
        mixed_proxy=dict(identity='DISCLOSED_ROUNDED_WINE_REVENUE_AND_VOLUME_PERCENTAGES',
            source_binding=dict(bindings[0], page=10), revenue_yoy_pct=revenue_rows[0][3],
            volume_yoy_pct=volume_rows[0][4], revenue_excerpt=industry.strip(), volume_excerpt=volume.strip(),
            identity_class='SOURCE_FACT_ROUNDED_NOT_PURE_PRICE'))
