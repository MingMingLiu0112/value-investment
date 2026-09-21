"""Hash-pinned single-file deployment after original-report batch checks."""
from deploy_memory_refresh import main


if __name__ == '__main__':
    main(expected={
        'adapters.py': (
            'c90313d1a2a969ee6eabbca46c1482637b2e82fab1c4ebf057237a8ad16791cc',
            '9555cfc316d8128680cae3bf9becbce6532f7289a9eadd7697ef6f11b94bc956',
        ),
    }, backup_prefix='attributable-profit-adapter-')
