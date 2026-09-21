"""Hash-pinned deployment of bounded recurring filing collection."""
from deploy_memory_refresh import main


EXPECTED = {
    'db.py': (
        'baf7cf6659e2b34b8192446bb43ae779debd6c96da772f9610c45c5bd1a0b9bd',
        '0548178e2f6f7655628bdb8cdca5b5177a81bbce3468f125df7cf71ef48249e3'),
}


if __name__ == '__main__':
    main(EXPECTED, backup_prefix='filing-refresh-queue-')
