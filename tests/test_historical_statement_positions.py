import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recover_moutai_historical_operating import statement
from recover_moutai_historical_capital import layout_current_value


def test_spaced_parent_heading_ends_consolidated_scope():
    rows=statement(['合 并 资 产 负 债 表\n存货 100.00 80.00\n母 公 司 资 产 负 债 表\n存货 999.00 888.00'], '资产负债表')
    assert len(rows)==1
    assert '100.00' in rows[0][1]
    assert '999.00' not in rows[0][1]


def test_blank_current_never_uses_note_or_comparative():
    text='\n'.join([
        f"{'货币资金':<20}{'100,000.00':>20}{'90,000.00':>25}",
        f"{'预付款项':<20}{'10,000.00':>20}{'9,000.00':>25}",
        f"{'存货':<20}{'50,000.00':>20}{'45,000.00':>25}",
        f"{'应收账款 4':<20}{'':>20}{'':>25}",
        f"{'预收款项':<20}{'':>20}{'13,740,329,698.82':>25}",
    ])
    assert layout_current_value(text,'货币资金')[0]=='100000.00'
    assert layout_current_value(text,'应收账款')[0] is None
    assert layout_current_value(text,'预收款项')[0] is None
