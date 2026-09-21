"""Deploy reviewed notice classification and rejected-disclosure queue filter."""
from deploy_memory_refresh import main

EXPECTED = {
    'disclosures.py': (
        'afd71d0e563c133d6567f4698eca9277882c1de86561737c0f4fb7df4ca0bcbe',
        '7894f51b35ac35bb77caa7916d97dc574cb4b297750bef5bccedf1eb7df06970'),
    'db.py': (
        '84e46b7e40094941731adb89499c9c687eb2efcf44f0b95ad8d560cdd9326f60',
        'baf7cf6659e2b34b8192446bb43ae779debd6c96da772f9610c45c5bd1a0b9bd'),
}


if __name__ == '__main__':
    main(EXPECTED, backup_prefix='report-notice-fix-')
