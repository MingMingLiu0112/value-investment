"""Deploy only the reviewed income queue and requested-period fixes."""
from deploy_memory_refresh import main


if __name__ == '__main__':
    main(expected={'cli.py': (
        'a59782f4374717742cd7d8ace2f8a9ab9fac457deef413a5a230f1791c721f0c',
        'b9816678d2f9c5004141fb67717341dcf10a561b6036c4723d0648b99e2d628b',
    )}, backup_prefix='income-collection-period-')
