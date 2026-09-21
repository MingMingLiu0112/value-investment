"""Conservative candidate extraction from explicitly ordered four-column tables."""
import re
from decimal import Decimal


def extract_combined_totals(pages):
    rows = []
    for page_number, text in enumerate(pages, 1):
        if not re.search(r'^[ \t]*合并及公司资产负债表(?:[ \t]*[（(]续[）)])?[ \t\r]*$', text, re.MULTILINE):
            continue
        if not re.search(r'^[ \t]*合并\s+合并\s+公司\s+公司\s*$', text, re.MULTILINE):
            continue
        header = re.search(r'附注\s+(20\d{2})\s*年\s+(20\d{2})\s*年\s+(20\d{2})\s*年\s+(20\d{2})\s*年', text)
        if not header or header[1] != header[3] or header[2] != header[4] or int(header[1]) != int(header[2])+1:
            continue
        if '(除特别注明外，金额单位为人民币千元)' not in text:
            continue
        if re.search(r'单位\s*[：:]|人民币(?:百万元|万元|亿元)', text):
            continue
        for label, field in [('资产总计','total_assets'),('负债合计','total_liabilities')]:
            number = r'(\d[\d,]*(?:\.\d+)?)'
            match = re.search(r'^[ \t]*'+label+r'\s+'+r'\s+'.join([number]*4)+r'[ \t\r]*$', text, re.MULTILINE)
            if not match:
                continue
            rows.append({'field_name':field,'source_label':label,'value':str(Decimal(match[1].replace(',',''))*1000),
                'unit':'CNY','page':page_number,'excerpt':header[0]+'\n合并 合并 公司 公司\n'+match[0],
                'status':'candidate_pending_automated_verification'})
    return rows
