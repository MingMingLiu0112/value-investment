from value_investment_agent.corporate_actions import extract_distribution_dates


def test_line_wrapped_dates_and_distinct_listing_date():
    rows = extract_distribution_dates([
        '股权登记日：2015 年7月16日 除权（除息）日：2015年7月17日',
        '新增无限售条件流通股份上市日：2015年7月20日 现金红利发放日：2015年7月17日'])
    assert {(r['field'], r['value'], r['page']) for r in rows} == {
        ('record_date', '2015-07-16', 1), ('ex_date', '2015-07-17', 1),
        ('bonus_listing_date', '2015-07-20', 2), ('cash_payment_date', '2015-07-17', 2)}
    assert not any(r['verified'] for r in rows)


def test_correction_preserves_both_candidates():
    rows = extract_distribution_dates([
        '更正前：现金红利将于2020年6月2日到账。更正后：现金红利将于2021年6月2日到账。'])
    assert [r['value'] for r in rows] == ['2020-06-02', '2021-06-02']


def test_no_guessing_across_table_headers_or_invalid_dates():
    assert extract_distribution_dates(['股权登记日 除权除息日 2021-06-01 2021-06-02']) == []
    assert extract_distribution_dates(['股权登记日：2021年2月30日']) == []


def test_exact_a_share_table_keeps_placeholder_column():
    rows = extract_distribution_dates([
        '股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n'
        'Ａ股 2017/7/6 － 2017/7/7 2017/7/10'])
    assert [(r['field'], r['value']) for r in rows] == [
        ('record_date', '2017-07-06'), ('ex_date', '2017-07-07'),
        ('cash_payment_date', '2017-07-10')]


def test_table_rejects_missing_columns_h_shares_and_bad_dates():
    header = '股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n'
    for row in ('A股 2017/7/6 2017/7/7 2017/7/10',
                'H股 2017/7/6 - 2017/7/7 2017/7/10',
                'A股 2017/7/6 - 2017/7/7 2017/2/30'):
        assert extract_distribution_dates([header + row]) == []
