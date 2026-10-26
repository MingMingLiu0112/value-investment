"""Retained official issuer layout adapter; no research/valuation/admission logic."""
from hashlib import sha256
from decimal import Decimal, localcontext
from pathlib import Path
import re

from .pdf_text import extract_pages


PARSER_VERSION = 'operating-erosion-sources-v1'


def read_product_revenue_sources(*, root: Path, sources: list, interim_revenue: str) -> dict:
    """Read the current H1 product table; do not invent TTM product revenues."""
    matches = [row for row in sources if row.get('id') == 'cninfo:1225475868']
    url = 'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF'
    if (len(matches) != 1 or matches[0].get('kind') != 'official_issuer_filing'
            or matches[0].get('issuer_identity', {}).get('security_code') != '600519'
            or matches[0].get('location') != url):
        raise ValueError('Product revenue requires the bound official H1 issuer filing')
    source = matches[0]
    root = root.resolve()
    path = (root/source['local_path']).resolve()
    if (not path.is_relative_to(root) or path.relative_to(root).as_posix() != source['local_path']
            or sha256(path.read_bytes()).hexdigest() != source['sha256']):
        raise ValueError('Product revenue source path/hash drift')
    page = extract_pages(path, limit=8)[7]
    compact = re.sub(r'\s+', '', page)
    if ('贵州茅台酒股份有限公司2026年半年度报告' not in compact
            or compact.count('3、销售情况') != 1 or compact.count('4、经销商情况') != 1):
        raise ValueError('Product revenue owner/table boundaries unsupported')
    table = compact.split('3、销售情况', 1)[1].split('4、经销商情况', 1)[0]
    if ('单位：万元币种：人民币' not in table
            or '茅台酒系列酒直销批发代理国内国外' not in table):
        raise ValueError('Product revenue currency/unit/column identity unsupported')
    rows = re.findall(r'([\d,]+\.\d{2})', table.split('报告期主要业务收入', 1)[1].split('注：', 1)[0])
    if len(rows) != 6:
        raise ValueError('Exact product/channel/geography current-period amounts required')
    with localcontext() as context:
        context.prec = 48
        values = [Decimal(row.replace(',', '')) * 10000 for row in rows]
        total = Decimal(interim_revenue)
        if (not total.is_finite() or min(values) < 0 or total <= 0
                or values[0]+values[1] != values[2]+values[3]
                or values[0]+values[1] != values[4]+values[5]
                or values[0]+values[1] > total):
            raise ValueError('Product/channel/geography/statement amounts do not reconcile')
        amounts = dict(moutai=str(values[0]), series=str(values[1]),
                       other=str(total-values[0]-values[1]))
    if sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Product revenue source changed during extraction')
    return dict(parser_version='moutai-h1-product-revenue-v1', period='H12026',
        identity_class='SOURCE_FACT_WITH_DERIVED_OTHER_REVENUE', unit='CNY',
        product_revenue_cny=amounts,
        other_revenue_basis='Statement operating revenue minus disclosed wine revenue; not zero.',
        ttm_product_revenue_status='NOT_DISCLOSED_BY_THIS_TABLE',
        source_binding=dict(path=source['local_path'], sha256=source['sha256']),
        source_url=url, physical_page=8, excerpt=table)


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
