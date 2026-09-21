"""Replay reviewed 2024 annual-report cells into a research-only input pack."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[1]
RELATIVE = 'runtime/historical-filing-index/20260908T041326996681Z/pdfs/600519-1222993920.pdf'
EXPECTED = '5299f4940e2ce4e91084b73dc457d558b9d335fa76fbfee6227e4254eb7f4a30'
# Physical page, reviewed row label and adjacent cells, including comparison columns.
ROWS = {
    'revenue': (8, '营业收入', ['170,899,152,276.34', '147,693,604,994.14']),
    'cfo': (8, '经营活动产生的现金流量净额', ['92,463,692,168.43', '66,593,247,721.09']),
    'liquor_revenue': (9, '酒类', ['170,611,838,052.02', '13,629,995,812.89']),
    'moutai_revenue': (9, '茅台酒', ['145,928,075,955.31', '8,662,079,388.78']),
    'series_revenue': (9, '其他系列酒', ['24,683,762,096.71', '4,967,916,424.11']),
    'wholesale_revenue': (9, '批发代理', ['95,768,511,021.23', '10,136,042,973.30']),
    'direct_revenue': (9, '直销', ['74,843,327,030.79', '3,493,952,839.59']),
    'deposit_inflow': (12, '客户存款和同业存放款项净增加额', ['11,060,205,782.10', '-810,223,002.76']),
    'capex_cash': (12, '购建固定资产、无形资产和其他长期资产支付的现金', ['4,678,712,053.56', '2,619,755,888.79']),
    'contract_liability': (13, '合同负债', ['9,592,453,014.66', '3.21', '14,125,755,802.29']),
    'group_deposits': (13, '吸收存款及同业存放', ['23,102,858,820.97', '7.73', '12,034,492,909.95']),
    'i_moutai_revenue': (16, '“i茅台”数字营销平台中、高档酒', ['2,002,366.62', '2,237,432.35']),
    'total_revenue': (63, '一、营业总收入', ['174,144,069,958.25', '150,560,330,316.45']),
    'financial_interest_revenue': (63, '利息收入41', ['3,244,917,681.91', '2,866,725,322.31']),
    'total_cost': (63, '二、营业总成本', ['54,523,971,452.57', '46,960,889,468.54']),
    'cost_of_sales': (63, '其中：营业成本40', ['13,789,482,367.98', '11,867,273,851.78']),
    'financial_interest_expense': (63, '利息支出41', ['105,127,802.03', '113,500,129.93']),
    'financial_commission_expense': (63, '手续费及佣金支出41', ['94,078.17', '68,578.57']),
    'business_taxes': (63, '税金及附加42', ['26,926,161,474.99', '22,234,175,898.60']),
    'selling_expense': (63, '销售费用43', ['5,639,300,059.49', '4,648,613,585.82']),
    'administrative_expense': (63, '管理费用44', ['9,315,650,060.38', '9,729,389,252.31']),
    'research_expense': (63, '研发费用45', ['218,375,472.87', '157,371,873.01']),
    'finance_expense_net': (63, '财务费用46', ['-1,470,219,863.34', '-1,789,503,701.48']),
    'other_income': (63, '加：其他收益47', ['21,229,466.81', '34,644,873.86']),
    'investment_income': (63, '投资收益（损失以“－”号填列）48', ['9,130,340.37', '34,025,967.82']),
    'fair_value_income': (64, '公允价值变动收益（损失以“－”号填列）49', ['60,980,724.35', '3,151,962.50']),
    'credit_loss_signed': (64, '信用减值损失（损失以“-”号填列）50', ['-23,248,436.03', '37,871,293.26']),
    'asset_disposal_income': (64, '资产处置收益（损失以“－”号填列）51', ['388,852.05', '-479,736.97']),
    'operating_profit': (64, '三、营业利润（亏损以“－”号填列）', ['119,688,579,453.23', '103,708,655,208.38']),
    'nonoperating_income': (64, '加：营业外收入52', ['70,936,575.97', '86,779,655.95']),
    'nonoperating_expense': (64, '减：营业外支出53', ['120,937,834.74', '132,881,174.52']),
    'pretax_profit': (64, '四、利润总额（亏损总额以“－”号填列）', ['119,638,578,194.46', '103,662,553,689.81']),
    'income_tax_expense': (64, '减：所得税费用54', ['30,303,850,168.56', '26,141,077,412.01']),
    'consolidated_profit': (64, '五、净利润（净亏损以“－”号填列）', ['89,334,728,025.90', '77,521,476,277.80']),
    'parent_profit': (64, '1.归属于母公司股东的净利润（净亏损以“-”号填列）', ['86,228,146,421.62', '74,734,071,550.75']),
    'minority_profit': (64, '2.少数股东损益（净亏损以“-”号填列）', ['3,106,581,604.28', '2,787,404,727.05']),
}


def compact(text):
    return re.sub(r'\s+', '', text)


def main():
    path = ROOT / RELATIVE
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('Annual-report original hash mismatch')
    index_path = next(path.parent.parent.glob('600519-1-*.json'))
    index = json.loads(index_path.read_text(encoding='utf-8'))
    matches = [row for row in index['response']['announcements']
               if row['announcementId'] == '1222993920' and row['secCode'] == '600519']
    if len(matches) != 1 or matches[0]['announcementTitle'] != '贵州茅台2024年年度报告':
        raise ValueError('Issuer/report identity mismatch')
    url = 'https://static.cninfo.com.cn/' + matches[0]['adjunctUrl']
    reader = PdfReader(path)
    facts = {}
    with pdfium.PdfDocument(path) as document:
        for name, (number, label, tokens) in ROWS.items():
            text1 = compact(reader.pages[number - 1].extract_text())
            page = document[number - 1]
            textpage = page.get_textpage()
            try:
                text2 = compact(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
            expected_row = compact(label + ''.join(tokens))
            if expected_row not in text1 or expected_row not in text2:
                raise ValueError(f'Reviewed row changed or absent: {name} p{number}')
            facts[name] = {
                'value': tokens[0].replace(',', ''),
                'unit': 'CNY ten_thousand' if name == 'i_moutai_revenue' else 'CNY',
                'period_end': '2024-12-31', 'physical_page': number,
                'period_basis': 'instant' if name in {'contract_liability', 'group_deposits'} else 'FY',
                'reviewed_row': label, 'reported_cells': tokens,
                'source_url': url, 'document_hash': EXPECTED,
                'status': 'reviewed_original_row_not_production_approved',
            }
    value = lambda key: Decimal(facts[key]['value'])
    operating_cost_keys = ('cost_of_sales', 'business_taxes', 'selling_expense',
                           'administrative_expense', 'research_expense')
    cost_keys = (*operating_cost_keys, 'financial_interest_expense',
                 'financial_commission_expense', 'finance_expense_net')
    gain_keys = ('other_income', 'investment_income', 'fair_value_income',
                 'credit_loss_signed', 'asset_disposal_income')
    # This residual includes consolidated expenses, not a separately disclosed
    # industrial segment. It must not be silently promoted to industrial EBIT.
    operating_residual = value('revenue') - sum(value(key) for key in operating_cost_keys)
    finance_bridge = (value('financial_interest_revenue') - value('financial_interest_expense')
                      - value('financial_commission_expense') - value('finance_expense_net'))
    other_gains = sum(value(key) for key in gain_keys)
    checks = {
        'product_revenue_sum': value('moutai_revenue') + value('series_revenue') == value('liquor_revenue'),
        'channel_revenue_sum': value('wholesale_revenue') + value('direct_revenue') == value('liquor_revenue'),
        'financial_revenue_bridge': value('revenue') + value('financial_interest_revenue') == value('total_revenue'),
        'profit_ownership_bridge': value('parent_profit') + value('minority_profit') == value('consolidated_profit'),
        'total_cost_bridge': sum(value(key) for key in cost_keys) == value('total_cost'),
        'operating_profit_bridge': operating_residual + finance_bridge + other_gains == value('operating_profit'),
        'pretax_profit_bridge': value('operating_profit') + value('nonoperating_income') - value('nonoperating_expense') == value('pretax_profit'),
        'tax_to_net_profit_bridge': value('pretax_profit') - value('income_tax_expense') == value('consolidated_profit'),
    }
    if not all(checks.values()):
        raise ValueError('Annual-report arithmetic bridge failed')
    derived = {
        'moutai_share_of_liquor_revenue': value('moutai_revenue') / value('liquor_revenue'),
        'direct_share_of_liquor_revenue': value('direct_revenue') / value('liquor_revenue'),
        'cfo_to_consolidated_profit_not_operating_segment_ratio': value('cfo') / value('consolidated_profit'),
        'cfo_less_capex_not_fcff': value('cfo') - value('capex_cash'),
        'deposit_inflow_share_of_cfo': value('deposit_inflow') / value('cfo'),
        'revenue_less_consolidated_operating_costs_not_segment_ebit': operating_residual,
        'financial_and_net_finance_expense_bridge': finance_bridge,
        'other_signed_gains_bridge': other_gains,
        'business_taxes_to_revenue': value('business_taxes') / value('revenue'),
        'accounting_effective_tax_rate_not_cash_tax_rate': value('income_tax_expense') / value('pretax_profit'),
    }
    stamp = datetime.now(timezone.utc)
    target = ROOT / 'runtime/company-research' / ('600519-' + stamp.strftime('%Y%m%dT%H%M%S%fZ'))
    target.mkdir(parents=True, exist_ok=False)
    result = {
        'symbol': '600519', 'report_year': 2024, 'generated_at': stamp.isoformat(),
        'source_path': RELATIVE, 'source_url': url, 'source_sha256': EXPECTED,
        'index_sha256': hashlib.sha256(index_path.read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'facts': facts, 'arithmetic_checks': checks,
        'derived_research_only': {key: str(number) for key, number in derived.items()},
        'operating_profit_lineage': {
            'residual_formula': 'revenue - sum(operating_cost_keys)',
            'operating_cost_keys': operating_cost_keys,
            'financial_bridge_formula': 'financial_interest_revenue - financial_interest_expense - financial_commission_expense - finance_expense_net',
            'other_gain_keys': gain_keys,
            'reconciliation': 'residual + financial_bridge + sum(other_gain_keys) = operating_profit',
            'industrial_segment_approved': False,
            'cash_tax_approved': False,
            'missing_scope': 'Allocation/elimination of financial subsidiary overhead and tax; accounting tax is not cash tax',
        },
        'validation_scope': 'Reviewed row adjacency in two decoders of ONE issuer PDF; no independent source confirmation',
        'current_valuation_approved': False, 'historical_strategy_approved': False,
        'gaps': ['Latest financial reports and current share basis',
                 'Separate industrial and financial subsidiary cash flows and claims',
                 'Restricted cash, nonoperating assets, debt, minorities and dilution',
                 'Independent peer/channel evidence and multi-year business comparison',
                 'Scenario drivers, reinvestment and dated discount-rate evidence',
                 'Historical availability and full trading execution chain'],
    }
    (target / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(target / 'evidence.json'), 'reviewed_rows': len(facts),
                      'arithmetic_checks': checks, 'derived_research_only': result['derived_research_only']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
