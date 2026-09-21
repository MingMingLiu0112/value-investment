"""Hash-pinned deployment of the official third-quarter category correction."""
from deploy_memory_refresh import main


EXPECTED = {
    'disclosures.py': (
        '0fc604e78f57d19ab4ebd05043ba24fcefb974f4f9f6668f75a72df4f849dd05',
        'd28f4291751f9122a2d550a34ee1aa6a7c30e3f6a74c3e74a36f29ce3f97f145'),
}


if __name__ == '__main__':
    main(EXPECTED, backup_prefix='third-quarter-category-')
