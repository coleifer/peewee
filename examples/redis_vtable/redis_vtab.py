#!/usr/bin/env python

import json

import apsw
from playhouse.apsw_ext import *
from redis import Redis


class RedisModule(object):
    def __init__(self, db):
        self.db = db

    def Create(self, db, modulename, dbname, tablename, *args):
        schema = 'CREATE TABLE %s (rowid, key, value, type, parent);'
        return schema % tablename, RedisTable(tablename, self.db)

    Connect = Create


class RedisTable(object):
    def __init__(self, name, db, columns=None, data=None):
        self.name = name
        self.db = db
        self._columns = ['rowid', 'key', 'value', 'type', 'parent']

    def BestIndex(self, constraints, orderbys):
        """
        Example query:

        SELECT * FROM redis_tbl
        WHERE parent = 'my-hash' AND type = 'hash';

        Since parent is column 4 and type is colum 3, the constraints will be:

        (4, apsw.SQLITE_INDEX_CONSTRAINT_EQ),
        (3, apsw.SQLITE_INDEX_CONSTRAINT_EQ)

        Ordering will be a list of 2-tuples consisting of the column index
        and boolean for descending.

        Return values are:

        * Constraints used, which for each constraint, must be either None,
          an integer (the argument number for the constraints passed into the
          Filter() method), or (int, bool) tuple.
        * Index number (default zero).
        * Index string (default None).
        * Boolean whether output will be in same order as the ordering specified.
        * Estimated cost in disk operations.
        """
        constraints_used = []
        columns = []
        for i, (column_idx, comparison) in enumerate(constraints):
            # Instruct SQLite to pass the constraint value to the Cursor's
            # Filter() method.
            constraints_used.append(i)

            # We will generate a string containing the columns being filtered
            # on, otherwise our Cursor won't know which columsn the filter
            # values correspond to.
            columns.append(self._columns[column_idx])

        return [
            constraints_used,  # Indices of constraints we are interested in.
            0,  # The index number, not used by us.
            ','.join(columns),  # The index name, a list of filter columns.
            False,  # Whether the results are ordered.
            1000 if 'parent' in columns else 10000,  # Query cost.
        ]

    def Open(self):
        return Cursor(self.db)

    def Disconnect(self):
        pass

    Destroy = Disconnect

    def UpdateChangeRow(self, rowid, newrowid, fields):
        pass

    def UpdateDeleteRow(self, rowid):
        pass

    def UpdateInsertRow(self, rowid, fields):
        # Return a rowid.
        pass


class Cursor(object):
    def __init__(self, db):
        self.db = db
        self.data = None
        self.index = 0
        self.nrows = None

    def Close(self):
        pass

    def Column(self, number):
        """
        Requests the value of the specified column number of the current row.
        If number is -1 then return the rowid.

        Return must be one of the 5 supported types.
        """
        return self.data[self.index][number]

    def Eof(self):
        """
        Called to ask if we are at the end of the table. It is called after
        each call to Filter and Next.

        Return `False` if at a valid row of data, else `True`.
        """
        return self.index == len(self.data)

    def get_data_for_key(self, key):
        # 'rowid', 'key', 'value', 'type', 'parent'
        key_type = self.db.type(key)
        if key_type == 'list':
            return [
                (i, i, value, 'list', key)
                for i, value in enumerate(self.db.lrange(key, 0, -1))]
        elif key_type == 'set':
            return [
                (i, value, None, 'set', key)
                for i, value in enumerate(self.db.smembers(key))]
        elif key_type == 'zset':
            all_members = self.db.zrange(key, 0, -1, withscores=True)
            return [
                (i, value, score, 'zset', key)
                for i, (value, score) in enumerate(all_members)]
        elif key_type == 'hash':
            return [
                (i, k, v, 'hash', key)
                for i, (k, v) in enumerate(self.db.hgetall(key).iteritems())]
        elif key_type == 'none':
            return []
        else:
            return [(1, key, self.db.get(key), 'string', key)]

    def Filter(self, indexnum, indexname, constraintargs):
        """
        This method is always called first to initialize an iteration to the
        first row of the table. The arguments come from the BestIndex() method
        in the table object with constraintargs being a tuple of the
        constraints you requested. If you always return None in BestIndex then
        indexnum will be zero, indexstring will be None and constraintargs
        will be empty).
        """
        columns = indexname.split(',')
        column_to_value = dict(zip(columns, constraintargs))
        if 'parent' in column_to_value:
            initial_key = column_to_value['parent']
            data = self.get_data_for_key(initial_key)
        else:
            data = []
            for i, key in enumerate(self.db.keys()):
                key_type = self.db.type(key)
                if key_type == 'string':
                    value = self.db.get(key)
                else:
                    value = None
                data.append((i, key, value, None, key_type))

        self.data = data
        self.index = 0
        self.nrows = len(data)

    def Next(self):
        """
        Move the cursor to the next row. Do not have an exception if there is
        no next row. Instead return False when Eof() is subsequently called.

        If you said you had indices in your VTTable.BestIndex() return, and
        they were selected for use as provided in the parameters to Filter()
        then you should move to the next appropriate indexed and constrained
        row.
        """
        self.index += 1

    def Rowid(self):
        """Return the current rowid."""
        return self.data[self.index][0]

database = APSWDatabase(':memory:')
redis = Redis()

redis_vtable = RedisModule(redis)
database.register_module('redis', redis_vtable)

class RedisView(VirtualModel):
    rowid = VirtualField()
    key = VirtualField()
    value = VirtualField()
    type = VirtualField()
    parent = VirtualField()

    _extension = 'redis'

    class Meta:
        database = database
        primary_key = False

def main():
    RedisView.create_table()
    query = RedisView.select(
        RedisView.key,
        RedisView.value,
        RedisView.type,
        RedisView.parent)

    print 'Listing all keys and values where possible.'
    for obj in query.dicts():
        print obj

    types = (
        ('Set', 'my-set'),
        ('ZSet', 'my-zset'),
        ('Hash', 'my-hash'),
        ('List', 'my-list'))
    for type_name, key in types:
        print 'Listing details for a %s...' % type_name
        for record in query.where(RedisView.parent == key).dicts():
            print record

if __name__ == '__main__':
    main()
