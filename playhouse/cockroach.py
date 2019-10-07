import re

from peewee import *


class CockroachDatabase(PostgresqlDatabase):
    field_types = PostgresqlDatabase.field_types
    field_types.update({
        'BLOB': 'BYTES',
    })

    for_update = False
    nulls_ordering = False

    def _set_server_version(self, conn):
        curs = conn.cursor()
        curs.execute('select version()')
        raw, = curs.fetchone()
        match_obj = re.match('^CockroachDB.+?v(\d+)\.(\d+)\.(\d+)', raw)
        if match_obj is not None:
            clean = '%d%02d%02d' % tuple(int(i) for i in match_obj.groups())
            self.server_version = int(clean)  # 19.1.5 -> 190105.
        else:
            # Fallback to use whatever cockroach tells us via protocol.
            super(CockroachDatabase, self)._set_server_version(conn)

    def conflict_statement(self, on_conflict, query):
        if not on_conflict._action: return

        action = on_conflict._action.lower()
        if action in ('replace', 'upsert'):
            return SQL('UPSERT')
        elif action not in ('ignore', 'nothing', 'update'):
            raise ValueError('Un-supported action for conflict resolution. '
                             'Cockroach supports REPLACE (UPSERT), IGNORE and '
                             'UPDATE.')

    def conflict_update(self, oc, query):
        action = oc._action.lower() if oc._action else ''
        if action in ('ignore', 'nothing'):
            return SQL('ON CONFLICT DO NOTHING')
        elif action in ('replace', 'upsert'):
            # No special stuff is necessary, this is just indicated by starting
            # the statement with UPSERT instead of INSERT.
            return
        elif oc._conflict_constraint:
            raise ValueError('Cockroach does not support the usage of a '
                             'constraint name. Use the column(s) instead.')

        return super(CockroachDatabase, self).conflict_update(oc, query)

    def extract_date(self, date_part, date_field):
        return fn.extract(date_part, date_field)
