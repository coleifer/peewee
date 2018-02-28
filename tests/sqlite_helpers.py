from peewee import sqlite3


def json_installed():
    if sqlite3.sqlite_version_info < (3, 9, 0):
        return False
    # Test in-memory DB to determine if the FTS5 extension is installed.
    tmp_db = sqlite3.connect(':memory:')
    try:
        tmp_db.execute('select json(?)', (1337,))
    except:
        return False
    finally:
        tmp_db.close()
    return True
