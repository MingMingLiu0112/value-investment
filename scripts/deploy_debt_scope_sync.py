"""Hash-pinned two-file scope gate deployment; refuses active app containers."""
from deploy_memory_refresh import main

EXPECTED = {
    'quality.py': (
        'a3f669dddbf07a35aef19d91db9f0ec9fc3d487886f1475f2eb6971f26ab84a2',
        '950a7b54e69cc0f1b3466a9095dc94bf49afde477e8175eb07444c2b02bc1015'),
    'financial_quality.py': (
        '87caea9de4cf68696e6c9e3d39efc4faa56af71059e1c740bb793ebb8f3a6476',
        'f0b732b90942cc2c50096df771e08628532c76f0aaac1dff4065e4cafb20854c'),
}


if __name__ == '__main__':
    main(EXPECTED, backup_prefix='debt-scope-sync-')
