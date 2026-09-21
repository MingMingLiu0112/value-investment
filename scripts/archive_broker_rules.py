"""Archive the CSRC rules inspected in the browser, using the existing archiver."""
from urllib.parse import quote

import archive_trading_rules as archive


if __name__ == '__main__':
    attachment = quote('附件1：证券公司风险控制指标计算标准规定.pdf')
    archive.SOURCES = {
        'broker-management-166': 'https://www.csrc.gov.cn/csrc/c106256/c1653957/content.shtml',
        'broker-calculation-2024-notice': 'https://www.csrc.gov.cn/csrc/c101954/c7507765/content.shtml',
        'broker-calculation-2024': 'https://www.csrc.gov.cn/csrc/c101954/c7507765/7507765/files/' + attachment,
    }
    archive.EXPECTED = {
        'broker-management-166': ('风险覆盖率＝净资本/各项风险资本准备之和', '资本杠杆率不得低于8%',
                                  '预警标准是规定标准的120%', '以母公司数据为基础'),
        'broker-calculation-2024-notice': ('2025年1月1日', '2024', '13号'),
    }
    archive.main()
