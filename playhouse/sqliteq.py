import logging
import weakref
from threading import Event
from threading import Thread
try:
    from Queue import Queue
except ImportError:
    from queue import Queue

try:
    import gevent
    from gevent import Greenlet as GThread
    from gevent.event import Event as GEvent
    from gevent.queue import Queue as GQueue
except ImportError:
    GThread = GQueue = GEvent = None

from playhouse.sqlite_ext import SqliteExtDatabase


logger = logging.getLogger('peewee.sqliteq')


class ResultTimeout(Exception):
    pass


class AsyncCursor(object):
    __slots__ = ('sql', 'params', 'commit', 'timeout',
                 '_event', '_cursor', '_exc', '_idx', '_rows')

    def __init__(self, event, sql, params, commit, timeout):
        self._event = event
        self.sql = sql
        self.params = params
        self.commit = commit
        self.timeout = timeout
        self._cursor = self._exc = self._idx = self._rows = None

    def set_result(self, cursor, exc=None):
        self._cursor = cursor
        self._exc = exc
        self._idx = 0
        self._rows = cursor.fetchall() if exc is None else []
        self._event.set()
        return self

    def _wait(self, timeout=None):
        timeout = timeout if timeout is not None else self.timeout
        if not self._event.wait(timeout=timeout) and timeout:
            raise ResultTimeout('results not ready, timed out.')
        if self._exc is not None:
            raise self._exc

    def __iter__(self):
        self._wait()
        if self._exc is not None:
            raise self._exec
        return self

    def next(self):
        try:
            obj = self._rows[self._idx]
        except IndexError:
            raise StopIteration
        else:
            self._idx += 1
            return obj
    __next__ = next

    @property
    def lastrowid(self):
        self._wait()
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        self._wait()
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()

    def fetchall(self):
        return list(self)  # Iterating implies waiting until populated.

    def fetchone(self):
        self._wait()
        try:
            return next(self)
        except StopIteration:
            return None


THREADLOCAL_ERROR_MESSAGE = ('threadlocals cannot be set to True when using '
                             'the Sqlite thread / queue database. All queries '
                             'are serialized through a single connection, so '
                             'allowing multiple threads to connect defeats '
                             'the purpose of this database.')
WAL_MODE_ERROR_MESSAGE = ('SQLite must be configured to use the WAL journal '
                          'mode when using this feature. WAL mode allows '
                          'one or more readers to continue reading while '
                          'another connection writes to the database.')


class SqliteQueueDatabase(SqliteExtDatabase):
    def __init__(self, database, use_gevent=False, autostart=False, readers=1,
                 queue_max_size=None, results_timeout=None, *args, **kwargs):
        if kwargs.get('threadlocals'):
            raise ValueError(THREADLOCAL_ERROR_MESSAGE)

        kwargs['threadlocals'] = False
        kwargs['check_same_thread'] = False

        # Ensure that journal_mode is WAL. This value is passed to the parent
        # class constructor below.
        pragmas = self._validate_journal_mode(
            kwargs.pop('journal_mode', None),
            kwargs.pop('pragmas', None))

        # Reference to execute_sql on the parent class. Since we've overridden
        # execute_sql(), this is just a handy way to reference the real
        # implementation.
        Parent = super(SqliteQueueDatabase, self)
        self.__execute_sql = Parent.execute_sql

        # Call the parent class constructor with our modified pragmas.
        Parent.__init__(database, pragmas=pragmas, *args, **kwargs)

        self._autostart = autostart
        self._results_timeout = results_timeout
        self._num_readers = readers

        self._is_stopped = True
        self._thread_helper = self.get_thread_impl(use_gevent)(queue_max_size)
        self._create_queues_and_workers()
        if self._autostart:
            self.start()

    def get_thread_impl(self, use_gevent):
        return GreenletHelper if use_gevent else ThreadHelper

    def _validate_journal_mode(self, journal_mode=None, pragmas=None):
        if journal_mode and journal_mode.lower() != 'wal':
            raise ValueError(WAL_MODE_ERROR_MESSAGE)

        if pragmas:
            pdict = dict((k.lower(), v) for (k, v) in pragmas)
            if pdict.get('journal_mode', 'wal').lower() != 'wal':
                raise ValueError(WAL_MODE_ERROR_MESSAGE)

            return [(k, v) for (k, v) in pragmas
                    if k != 'journal_mode'] + [('journal_mode', 'wal')]
        else:
            return [('journal_mode', 'wal')]

    def _create_queues_and_workers(self):
        self._write_queue = self._thread_helper.queue()
        self._read_queue = self._thread_helper.queue()

        target = self._run_worker_loop
        self._writer = self._thread_helper.thread(target, self._write_queue)
        self._readers = [self._thread_helper.thread(target, self._read_queue)
                         for _ in range(self._num_readers)]

    def _run_worker_loop(self, queue):
        while True:
            async_cursor = queue.get()
            if async_cursor is StopIteration:
                logger.info('worker shutting down.')
                return

            logger.debug('received query %s', async_cursor.sql)
            self._process_execution(async_cursor)

    def _process_execution(self, async_cursor):
        try:
            cursor = self.__execute_sql(async_cursor.sql, async_cursor.params,
                                        async_cursor.commit)
        except Exception as exc:
            cursor = None
        else:
            exc = None
        return async_cursor.set_result(cursor, exc)

    def queue_size(self):
        return (self._write_queue.qsize(), self._read_queue.qsize())

    def execute_sql(self, sql, params=None, require_commit=True, timeout=None):
        cursor = AsyncCursor(
            event=self._thread_helper.event(),
            sql=sql,
            params=params,
            commit=require_commit,
            timeout=self._results_timeout if timeout is None else timeout)
        queue = self._write_queue if require_commit else self._read_queue
        queue.put(cursor)
        return cursor

    def start(self):
        with self._conn_lock:
            if not self._is_stopped:
                return False
            self._writer.start()
            for reader in self._readers:
                reader.start()
            logger.info('workers started.')
            self._is_stopped = False
            return True

    def stop(self):
        logger.debug('environment stop requested.')
        with self._conn_lock:
            if self._is_stopped:
                return False
            self._write_queue.put(StopIteration)
            for _ in self._readers:
                self._read_queue.put(StopIteration)
            self._writer.join()
            for reader in self._readers:
                reader.join()
            return True

    def is_stopped(self):
        with self._conn_lock:
            return self._is_stopped


class ThreadHelper(object):
    __slots__ = ('queue_max_size',)

    def __init__(self, queue_max_size=None):
        self.queue_max_size = queue_max_size

    def event(self): return Event()

    def queue(self, max_size=None):
        max_size = max_size if max_size is not None else self.queue_max_size
        return Queue(maxsize=max_size or 0)

    def thread(self, fn, *args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.daemon = True
        return thread


class GreenletHelper(ThreadHelper):
    __slots__ = ('queue_max_size',)

    def event(self): return GEvent()

    def queue(self, max_size=None):
        max_size = max_size if max_size is not None else self.queue_max_size
        return GQueue(maxsize=max_size or 0)

    def thread(self, fn, *args, **kwargs):
        def wrap(*a, **k):
            gevent.sleep()
            return fn(*a, **k)
        return GThread(wrap, *args, **kwargs)
