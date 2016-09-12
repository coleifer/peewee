import logging
from threading import Event
from threading import Lock
from threading import Thread
try:
    from Queue import Queue
except ImportError:
    from queue import Queue

try:
    from gevent import Greenlet as GThread
    from gevent.event import Event as GEvent
    from gevent.queue import Queue as GQueue
except ImportError:
    GThread = GQueue = GEvent = None

from playhouse.sqlite_ext import SqliteExtDatabase


logger = logging.getLogger('peewee.sqliteq')


class Environment(object):
    def __init__(self, queue_max_size=None):
        self._queue_max_size = queue_max_size
        self.queue = self.create_queue(queue_max_size)
        self.worker = self.create_worker()
        self._lock = Lock()
        self._stopped = True

    def worker_loop(self):
        while True:
            execution = self.queue.get()
            if execution is StopIteration:
                logger.info('worker shutting down.')
                return

            logger.debug('received query %s', execution)
            try:
                execution.execute()
            except Exception as exc:
                execution.set_exception(exc)
                logger.exception('error executing query: %s', execution)
            else:
                logger.debug('executed %s', execution)

    def start(self):
        with self._lock:
            if not self._stopped:
                logger.warning('start() called, but worker already running.')
                return False

            self.worker.start()
            self._stopped = False
            logger.info('worker started.')
            return True

    def stop(self, block=True, timeout=None):
        logger.debug('environment stop requested.')
        with self._lock:
            if not self._stopped:
                self.queue.put(StopIteration)
                self._stopped = True
                logger.debug('notified worker to finish work and stop.')
            if block:
                logger.debug('waiting %s for worker to finish.' %
                             (timeout or 'indefinitely'))
                self.worker.join(timeout=timeout)

        worker_finished = self.is_worker_stopped()
        logger.debug('returning from stop(), worker is %sfinished' %
                     ('' if worker_finished else 'not '))

        return worker_finished

    def create_worker(self):
        raise NotImplementedError

    def is_worker_stopped(self):
        raise NotImplementedError

    def create_queue(self, queue_max_size=None):
        raise NotImplementedError

    def create_event(self):
        raise NotImplementedError

    def get_queue_size(self):
        return self.queue.qsize()

    def enqueue(self, execution):
        self.queue.put(execution)


class ThreadEnvironment(Environment):
    def create_worker(self):
        worker = Thread(target=self.worker_loop, name='sqliteq-worker')
        worker.daemon = True
        return worker

    def is_worker_stopped(self):
        return not self.worker.isAlive()

    def create_event(self):
        return Event()

    def create_queue(self, queue_max_size=None):
        return Queue(maxsize=queue_max_size)


class GreenletEnvironment(Environment):
    def run(self, execution):
        super(GreenletEnvironment, self).run(execution)
        gevent.sleep()

    def create_worker(self):
        return GThread(run=self.worker_loop)

    def is_worker_stopped(self):
        return self.worker.dead

    def create_event(self):
        return GEvent()

    def create_queue(self, queue_max_size=None):
        return GQueue(maxsize=queue_max_size)


class Execution(object):
    def __init__(self, database, event, sql, params, require_commit=False):
        self.db = database
        self.event = event
        self.sql = sql
        self.params = params
        self.require_commit = require_commit

        # Don't want these to be manipulated by external objects.
        self.__cursor = None
        self.__idx = 0
        self.__exc = None
        self.__results = None
        self.__lastrowid = None
        self.__rowcount = None

    def __del__(self):
        if self.__cursor is not None:
            self.__cursor.close()

    def execute(self):
        self.__exc = None
        self.__cursor = self.db._process_execution(self)
        if self.__exc:
            raise self.__exc
        self.__populate()
        self.event.set()

    def __populate(self):
        self.__idx = 0
        self.__results = [row for row in self.__cursor]

    def set_exception(self, exc):
        self.__exc = exc

    def __iter__(self):
        return self

    def next(self):
        self.event.wait()
        try:
            obj = self.__results[self.__idx]
        except IndexError:
            raise StopIteration
        else:
            self.__idx += 1
            return obj
    __next__ = next

    @property
    def lastrowid(self):
        self.event.wait()
        return self.__cursor.lastrowid

    @property
    def rowcount(self):
        self.event.wait()
        return self.__cursor.rowcount

    @property
    def description(self):
        return self.__cursor.description

    def fetchall(self):
        return list(self)  # Iterating implies waiting until populated.

    def fetchone(self):
        return next(self)


class SqliteThreadDatabase(SqliteExtDatabase):
    def __init__(self, database, environment_type=None, queue_size=None,
                 *args, **kwargs):
        if kwargs.get('threadlocals'):
            raise ValueError('threadlocals cannot be set to True when using '
                             'the Sqlite thread / queue database. All queries '
                             'are serialized through a single connection, so '
                             'allowing multiple threads to connect defeats '
                             'the purpose of this database.')
        kwargs['threadlocals'] = False
        kwargs['check_same_thread'] = False

        # Reference to execute_sql on the parent class. Since we've overridden
        # execute_sql(), this is just a handy way to reference the real
        # implementation.
        self.__execute_sql = super(SqliteThreadDatabase, self).execute_sql

        super(SqliteThreadDatabase, self).__init__(database, *args, **kwargs)

        # The database needs to keep a reference to the environment being used,
        # since it will be enqueueing query executions.
        self._env_type = environment_type or ThreadEnvironment
        self.environment = self._env_type(queue_size)

    def _process_execution(self, execution):
        return self.__execute_sql(execution.sql, execution.params,
                                  execution.require_commit)

    def execute_sql(self, sql, params=None, require_commit=True):
        event = self.environment.create_event()
        execution = Execution(self, event, sql, params, require_commit)
        self.environment.enqueue(execution)
        return execution

    def start_worker(self):
        return self.environment.start()

    def shutdown(self, block=True, timeout=None):
        return self.environment.stop(block=block, timeout=timeout)

    def queue_size(self):
        return self.environment.get_queue_size()
