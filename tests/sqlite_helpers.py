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


def json_patch_installed():
    return sqlite3.sqlite_version_info >= (3, 18, 0)


def compile_option(p):
    if not hasattr(compile_option, '_pragma_cache'):
        conn = sqlite3.connect(':memory:')
        curs = conn.execute('pragma compile_options')
        opts = [opt.lower().split('=')[0].strip() for opt, in curs.fetchall()]
        compile_option._pragma_cache = set(opts)
    return p in compile_option._pragma_cache
