import asyncio
import tempfile
import os
import sys
import unittest
from unittest.mock import Mock, AsyncMock

from peewee import *
from playhouse.pwasyncio import *
from .base import MYSQL_PARAMS
from .base import PSQL_PARAMS

try:
    import asyncpg
except ImportError:
    asyncpg = None

try:
    import aiomysql
except ImportError:
    aiomysql = None

import aiosqlite

SQLITE_RETURNING = aiosqlite.sqlite_version_info >= (3, 35, 0)


# Test Models
class TestModel(Model):
    name = CharField()
    value = IntegerField(default=0)

class User(Model):
    username = CharField()

class Tweet(Model):
    user = ForeignKeyField(User, backref='tweets')
    message = TextField()


class TestGreenletSpawn(unittest.IsolatedAsyncioTestCase):
    async def test_simple_function(self):
        result = await greenlet_spawn(lambda x, y: x + y, 5, 3)
        self.assertEqual(result, 8)

    async def test_function_with_await(self):
        async def async_helper():
            await asyncio.sleep(0.01)
            return 2

        def func_with_await():
            return await_(async_helper()) * 2

        self.assertEqual(await greenlet_spawn(func_with_await), 4)

    async def test_multiple_awaits(self):
        async def fetch_value(val):
            await asyncio.sleep(0.01)
            return val

        def multi_await():
            return sum([await_(fetch_value(i)) for i in [10, 20, 30]])

        self.assertEqual(await greenlet_spawn(multi_await), 60)

    async def test_exception_propagation(self):
        def failing_func():
            raise ValueError('Test error')

        with self.assertRaises(ValueError):
            await greenlet_spawn(failing_func)

    async def test_exception_in_awaitable(self):
        async def failing_async():
            await asyncio.sleep(0.01)
            raise RuntimeError('Async error')

        with self.assertRaises(RuntimeError):
            await greenlet_spawn(lambda: await_(failing_async()))

    def test_await_outside_greenlet(self):
        with self.assertRaises(MissingGreenletBridge):
            await_(Mock())


class TestTaskLocal(unittest.IsolatedAsyncioTestCase):
    async def test_task_isolation(self):
        task_local = TaskLocal()

        async def task_worker(task_id):
            state = task_local._current()
            state.conn = task_id
            await asyncio.sleep(0.01)
            return task_local._current().conn

        results = await asyncio.gather(*[task_worker(i) for i in range(5)])
        self.assertEqual(results, [0, 1, 2, 3, 4])

    async def test_state_attributes(self):
        task_local = TaskLocal()
        task_local.conn = 'test_conn'
        task_local.closed = False
        task_local.transactions = [1, 2, 3]

        self.assertEqual(task_local.conn, 'test_conn')
        self.assertFalse(task_local.closed)
        self.assertEqual(task_local.transactions, [1, 2, 3])

    async def test_get_returns_state(self):
        state = TaskLocal().get()
        self.assertTrue(hasattr(state, 'transactions'))
        self.assertTrue(hasattr(state, 'conn'))
        self.assertEqual(state.transactions, [])
        self.assertTrue(state.closed)

    async def test_clear_removes_state(self):
        task_local = TaskLocal()
        task_local.conn = 'test'
        initial_key = task_local._get_storage_key()

        task_local.clear()
        self.assertNotIn(initial_key, task_local._state_storage)

    async def test_reset_clears_connection_state(self):
        task_local = TaskLocal()
        task_local.conn = 'test_conn'
        task_local.closed = False
        task_local.transactions = [1, 2]
        task_local.ctx = [9]

        task_local.reset()

        self.assertIsNone(task_local.conn)
        self.assertTrue(task_local.closed)
        self.assertEqual(task_local.transactions, [])
        self.assertEqual(task_local.ctx, [])

    async def test_set_connection(self):
        task_local = TaskLocal()
        mock_conn = Mock()

        task_local.set_connection(mock_conn)

        self.assertIs(task_local.conn, mock_conn)
        self.assertFalse(task_local.closed)

    async def test_cleanup_dead_tasks(self):
        task_local = TaskLocal()
        state = task_local._current()
        state.conn = 1

        # Add fake dead task
        dead_key = 999999
        task_local._state_storage[dead_key] = Mock()

        cleaned = task_local.cleanup_dead_tasks()

        self.assertGreaterEqual(cleaned, 1)
        self.assertNotIn(dead_key, task_local._state_storage)


class TestCursorAdapter(unittest.TestCase):
    def setUp(self):
        self.rows = [(1, 'a'), (2, 'b'), (3, 'c')]

    def test_fetchone(self):
        cursor = CursorAdapter(self.rows)
        self.assertEqual(cursor.fetchone(), (1, 'a'))
        self.assertEqual(cursor.fetchone(), (2, 'b'))
        self.assertEqual(cursor.fetchone(), (3, 'c'))
        self.assertIsNone(cursor.fetchone())

    def test_fetchall(self):
        cursor = CursorAdapter(self.rows)
        self.assertEqual(cursor.fetchall(), self.rows)

    def test_iteration(self):
        cursor = CursorAdapter(self.rows)
        self.assertEqual(list(cursor), self.rows)

    def test_rowcount(self):
        cursor = CursorAdapter(self.rows)
        self.assertEqual(cursor.rowcount, 3)

    def test_lastrowid(self):
        cursor = CursorAdapter(self.rows, lastrowid=1)
        self.assertEqual(cursor.lastrowid, 1)

    def test_description(self):
        desc = [('id',), ('name',)]
        cursor = CursorAdapter(self.rows, description=desc)
        self.assertEqual(cursor.description, desc)


class TestTaskLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_task_state_cleanup_after_completion(self):
        db = AsyncSqliteDatabase(':memory:')
        TestModel._meta.set_database(db)

        async with db:
            await db.acreate_tables([TestModel])

            async def task_with_state():
                async with db:
                    await db.run(TestModel.create, name='test', value=1)
                # State should be in storage
                key = db._state._get_storage_key()
                return key

            task_key = await task_with_state()

            # Task completed, manually trigger cleanup
            cleaned = db._state.cleanup_dead_tasks()

        await db.close_pool()

    async def test_concurrent_task_state_isolation(self):
        db = AsyncSqliteDatabase(':memory:')
        TestModel._meta.set_database(db)

        async with db:
            await db.acreate_tables([TestModel])

            task_states = []

            async def capture_state(task_id):
                async with db:
                    state_before = id(db._state.get())
                    await db.run(TestModel.create, name=f't{task_id}', value=task_id)
                    state_after = id(db._state.get())
                    return (state_before, state_after, state_before == state_after)

            results = await asyncio.gather(*[capture_state(i) for i in range(5)])

            # Each task should use same state throughout.
            for before, after, same in results:
                self.assertTrue(same)

        await db.close_pool()


class TestAsyncSQLiteConnection(unittest.IsolatedAsyncioTestCase):
    async def test_execute_returns_cursor_adapter(self):
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [(1, 'test')]
        mock_cursor.lastrowid = 1
        mock_cursor.description = [('id',), ('name',)]
        mock_conn.execute.return_value = mock_cursor

        conn = AsyncSQLiteConnection(mock_conn)
        result = await conn.execute('SELECT * FROM test')

        self.assertIsInstance(result, CursorAdapter)
        self.assertEqual(result.fetchall(), [(1, 'test')])
        self.assertEqual(result.lastrowid, 1)


class TestAsyncMySQLConnection(unittest.IsolatedAsyncioTestCase):
    async def test_execute_returns_cursor_adapter(self):
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [(1, 'test')]
        mock_cursor.lastrowid = 1
        mock_cursor.description = [('id',), ('name',)]
        mock_conn.cursor.return_value = mock_cursor

        conn = AsyncMySQLConnection(mock_conn)
        result = await conn.execute('SELECT * FROM test')

        self.assertIsInstance(result, CursorAdapter)
        self.assertEqual(result.fetchall(), [(1, 'test')])

    async def test_concurrent_access_serialized(self):
        mock_conn = AsyncMock()
        execution_order = []

        async def tracked_execute(sql, params):
            execution_order.append(f'start-{sql}')
            await asyncio.sleep(0.05)
            execution_order.append(f'end-{sql}')
            return []

        mock_cursor = AsyncMock()
        mock_cursor.execute = tracked_execute
        mock_conn.cursor.return_value = mock_cursor

        conn = AsyncMySQLConnection(mock_conn)
        await asyncio.gather(conn.execute('Q1', None), conn.execute('Q2', None))

        # One query should complete before the other starts
        q1_end = execution_order.index('end-Q1')
        q2_start = execution_order.index('start-Q2')
        q2_end = execution_order.index('end-Q2')
        q1_start = execution_order.index('start-Q1')

        self.assertTrue((q1_end < q2_start) or (q2_end < q1_start))


class TestAsyncPostgresqlConnection(unittest.IsolatedAsyncioTestCase):
    async def test_parameter_conversion(self):
        mock_conn = AsyncMock()
        mock_record = Mock()
        mock_record.keys.return_value = ['id', 'name']
        mock_conn.fetch.return_value = [mock_record]

        conn = AsyncPostgresqlConnection(mock_conn)
        await conn.execute('SELECT * FROM test WHERE id = %s AND name = %s',
                           (1, 'test'))

        # Verify conversion happened
        call_args = mock_conn.fetch.call_args
        self.assertIn('$1', call_args[0][0])
        self.assertIn('$2', call_args[0][0])
        self.assertNotIn('%s', call_args[0][0])

    async def test_concurrent_access_serialized(self):
        mock_conn = AsyncMock()
        execution_order = []

        async def tracked_fetch(sql, params=None):
            execution_order.append(f'start-{sql}')
            await asyncio.sleep(0.05)
            execution_order.append(f'end-{sql}')
            return []

        mock_conn.fetch = tracked_fetch

        conn = AsyncPostgresqlConnection(mock_conn)
        await asyncio.gather(conn.execute('Q1', None), conn.execute('Q2', None))

        # One query should complete before the other starts
        q1_end = execution_order.index('end-Q1')
        q2_start = execution_order.index('start-Q2')
        q2_end = execution_order.index('end-Q2')
        q1_start = execution_order.index('start-Q1')

        self.assertTrue((q1_end < q2_start) or (q2_end < q1_start))

    async def test_execute_without_params(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        conn = AsyncPostgresqlConnection(mock_conn)
        result = await conn.execute('SELECT * FROM test', None)

        mock_conn.fetch.assert_called_once_with('SELECT * FROM test')


class BaseDatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.db_file.name
        self.db_file.close()
        self.db = AsyncSqliteDatabase(self.db_path)
        TestModel._meta.set_database(self.db)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    async def asyncSetUp(self):
        await self.db.aconnect()
        await self.db.acreate_tables([TestModel])

    async def asyncTearDown(self):
        await self.db.aclose()
        await self.db.close_pool()

    async def create_record(self, name='test', value=1):
        return await self.db.run(TestModel.create, name=name, value=value)

    async def count_records(self):
        return await self.db.run(TestModel.select().count)


class TestConnectionValidation(BaseDatabaseTestCase):
    async def test_validation_detects_dead_connection(self):
        await self.db.aconnect()
        conn = self.db._state.conn

        # Simulate dead connection
        await conn.close()

        # Next operation should detect and replace
        await self.create_record('test', 1)

        # Should have new connection
        self.assertIsNot(self.db._state.conn, conn)
        self.assertEqual(await self.count_records(), 1)

    async def test_validation_timeout(self):
        db = AsyncSqliteDatabase(':memory:', validate_conn_timeout=0.001)
        await db.aconnect()

        # This should work even with very short timeout on valid conn
        await db.aclose()
        await db.close_pool()


class TestAsyncSqliteDatabase(BaseDatabaseTestCase):
    async def test_connect_creates_pool(self):
        await self.db.aclose()
        await self.db.close_pool()
        self.assertIsNone(self.db._pool)

        await self.db.aconnect()

        self.assertIsNotNone(self.db._pool)
        self.assertIsNotNone(self.db._state.conn)

        await self.db.aclose()
        self.assertIsNone(self.db._state.conn)

    async def test_execute_sql(self):
        await self.db.aexecute_sql(
            'CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)')
        await self.db.aexecute_sql(
            'INSERT INTO test (name) VALUES (?)', ('test_name',))

        result = await self.db.aexecute_sql('SELECT * FROM test')
        rows = result.fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 'test_name')

        await self.db.aclose()

    async def test_context_manager(self):
        async with self.db:
            self.assertIsNotNone(self.db._state.conn)
            self.assertFalse(self.db._state.closed)

        self.assertIsNone(self.db._state.conn)
        self.assertTrue(self.db._state.closed)

    async def test_multiple_tasks_isolation(self):
        await self.db.aconnect()
        await self.db.aexecute_sql(
            'CREATE TABLE test (id INTEGER PRIMARY KEY, value INTEGER)')

        async def task_worker(task_id):
            await self.db.aconnect()
            await self.db.aexecute_sql(
                'INSERT INTO test (value) VALUES (?)', (task_id,))
            result = await self.db.aexecute_sql(
                'SELECT value FROM test WHERE value = ?', (task_id,))
            rows = result.fetchall()
            await self.db.aclose()
            return rows

        results = await asyncio.gather(*[task_worker(i) for i in range(3)])

        self.assertEqual(sorted(results), [[(0,)], [(1,)], [(2,)]])
        await self.db.aclose()

    async def test_pragmas(self):
        db = AsyncSqliteDatabase(':memory:', pragmas={'user_version': '99'})
        conn = await db.aconnect()
        result = await conn.execute('PRAGMA user_version')
        self.assertEqual(result.fetchone(), (99,))
        await db.close_pool()

    async def test_custom_functions(self):
        db = AsyncSqliteDatabase(':memory:')

        @db.func()
        def title_case(s):
            return s.title()

        async with db:
            result = await db.aexecute_sql('SELECT title_case(?)',
                                                ('test foo',))
            self.assertEqual(result.fetchone(), ('Test Foo',))

        await db.close_pool()


class TestAsyncAtomic(BaseDatabaseTestCase):
    async def test_atomic_context_manager(self):
        async with self.db.atomic():
            await self.create_record('atomic_test', 123)

        self.assertEqual(await self.count_records(), 1)

        async with self.db.atomic() as txn:
            await self.create_record('atomic_test', 123)
            self.assertEqual(await self.count_records(), 2)
            await txn.arollback()
            self.assertEqual(await self.count_records(), 1)

        self.assertEqual(await self.count_records(), 1)

    async def test_transaction_commit(self):
        def create_in_transaction():
            with self.db.atomic():
                TestModel.create(name='tx1')
                TestModel.create(name='tx2')

        await self.db.run(create_in_transaction)
        self.assertEqual(await self.count_records(), 2)

    async def test_transaction_rollback(self):
        def failing_transaction():
            with self.db.atomic():
                TestModel.create(name='tx1')
                raise ValueError('fail')

        with self.assertRaises(ValueError):
            await self.db.run(failing_transaction)

        self.assertEqual(await self.count_records(), 0)

        async with self.db.atomic() as txn:
            await self.create_record('tx2')
            await txn.arollback()

        self.assertEqual(await self.count_records(), 0)

    async def test_nested_transactions(self):
        def nested_transactions():
            with self.db.atomic():
                TestModel.create(name='outer1', value=1)
                with self.db.atomic():
                    TestModel.create(name='inner1', value=2)
                    TestModel.create(name='inner2', value=3)
                TestModel.create(name='outer2', value=4)

        await self.db.run(nested_transactions)
        self.assertEqual(await self.count_records(), 4)

    async def test_nested_implicit_rollback(self):
        def nested_with_inner_rollback():
            with self.db.atomic():
                TestModel.create(name='outer1', value=1)
                try:
                    with self.db.atomic():
                        TestModel.create(name='inner1', value=2)
                        raise ValueError('fail')
                except ValueError:
                    pass
                TestModel.create(name='outer2', value=3)

        await self.db.run(nested_with_inner_rollback)
        self.assertEqual(await self.count_records(), 2)

    async def test_nested_explicit_rollback(self):
        def nested_with_inner_rollback():
            with self.db.atomic():
                TestModel.create(name='outer1')
                with self.db.atomic() as sp:
                    TestModel.create(name='inner1')
                    self.assertEqual(TestModel.select().count(), 2)
                    sp.rollback()

                self.assertEqual(TestModel.select().count(), 1)
                TestModel.create(name='outer2')

        await self.db.run(nested_with_inner_rollback)
        self.assertEqual(await self.count_records(), 2)

        async with self.db.atomic():
            await self.db.run(TestModel.create, name='outer3')
            async with self.db.atomic() as sp:
                await self.db.run(TestModel.create, name='inner2')
                self.assertEqual(await self.count_records(), 4)
                await sp.arollback()

            self.assertEqual(await self.count_records(), 3)
            await self.db.run(TestModel.create, name='outer4')

        self.assertEqual(await self.count_records(), 4)

    async def test_nested_mix(self):
        async with self.db.atomic():
            await self.create_record('t1')
            async with self.db.atomic():
                await self.create_record('t2')
                async with self.db.atomic():
                    await self.create_record('t3')

                try:
                    async with self.db.atomic():
                        await self.create_record('t4')
                        self.assertEqual(await self.count_records(), 4)
                        raise ValueError('fail')
                except ValueError:
                    pass

                async with self.db.atomic() as sp:
                    await self.create_record('t4')
                    self.assertEqual(await self.count_records(), 4)
                    await sp.arollback()

                self.assertEqual(await self.count_records(), 3)

            try:
                async with self.db.atomic():
                    await self.create_record('t5')
                    self.assertEqual(await self.count_records(), 4)
                    raise ValueError('fail')
            except ValueError:
                self.assertEqual(await self.count_records(), 3)

        self.assertEqual(await self.count_records(), 3)

        try:
            async with self.db.atomic():
                await self.create_record('t1')
                async with self.db.atomic():
                    await self.create_record('t2')
                    async with self.db.atomic():
                        await self.create_record('t3')
                        self.assertEqual(await self.count_records(), 6)
                raise ValueError('fail')
        except ValueError:
            pass

        self.assertEqual(await self.count_records(), 3)


class TestDatabaseHelpers(BaseDatabaseTestCase):
    async def test_aexecute(self):
        q = (TestModel
             .insert_many([(f'item{i}', i) for i in range(10)]))

        if SQLITE_RETURNING:
            q = q.returning(TestModel.name)
            res = await self.db.aexecute(q)
            self.assertEqual([t.name for t in res],
                             [f'item{i}' for i in range(10)])
        else:
            res = await self.db.aexecute(q)

        self.assertEqual(await self.count_records(), 10)

        q = (TestModel
             .update(value=TestModel.value * 10)
             .where(TestModel.value < 3))

        if SQLITE_RETURNING:
            q = q.returning(TestModel.name, TestModel.value)
            res = await self.db.aexecute(q)
            self.assertEqual(sorted([(t.name, t.value) for t in res]),
                             [('item0', 0), ('item1', 10), ('item2', 20)])
        else:
            res = await self.db.aexecute(q)

        q = TestModel.select().where(TestModel.value >= 10)
        self.assertEqual(await self.db.run(q.count), 2)

        rows = await self.db.aexecute(q.order_by(TestModel.value))
        self.assertEqual([r.name for r in rows], ['item1', 'item2'])

    async def test_list(self):
        for i in range(5):
            await self.create_record(f'item{i}', i)

        results = await self.db.list(TestModel.select())
        self.assertEqual(len(results), 5)
        self.assertIsInstance(results[0], TestModel)

    async def test_scalar(self):
        for i in range(10):
            await self.create_record(f'item{i}', i)

        max_val = await self.db.scalar(
            TestModel.select(fn.MAX(TestModel.value)))
        self.assertEqual(max_val, 9)

    async def test_get(self):
        record = await self.create_record('unique', 999)

        fetched = await self.db.get(
            TestModel.select().where(TestModel.name == 'unique'))
        self.assertEqual(fetched.id, record.id)

    async def test_get_not_found(self):
        with self.assertRaises(TestModel.DoesNotExist):
            await self.db.get(
                TestModel.select().where(TestModel.name == 'nonexistent'))

    async def test_list_empty_query(self):
        results = await self.db.list(TestModel.select())
        self.assertEqual(results, [])

    async def test_scalar_no_results(self):
        count = await self.db.scalar(TestModel.select(fn.COUNT(TestModel.id)))
        self.assertEqual(count, 0)

    async def test_iteration_empty_results(self):
        def iterate():
            return list(TestModel.select())

        results = await self.db.run(iterate)
        self.assertEqual(results, [])


class TestModelOperations(BaseDatabaseTestCase):
    async def test_create(self):
        record = await self.create_record('test1', 100)
        self.assertEqual(record.name, 'test1')
        self.assertEqual(record.value, 100)

    async def test_select(self):
        await self.create_record('test1', 100)

        records = await self.db.list(TestModel.select())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, 'test1')

    async def test_filter(self):
        for i in range(20):
            await self.create_record(f'item{i}', i * 10)

        query = TestModel.select().where(TestModel.value > 100)
        results = await self.db.list(query)
        self.assertEqual(len(results), 9)

    async def test_ordering(self):
        for i in range(20):
            await self.create_record(f'item{i}', i * 10)

        query = TestModel.select().order_by(TestModel.value.desc()).limit(5)
        results = await self.db.list(query)

        self.assertEqual(len(results), 5)
        self.assertEqual(results[0].value, 190)
        self.assertEqual(results[4].value, 150)

    async def test_aggregation(self):
        for i in range(20):
            await self.create_record(f'item{i}', i)

        count = await self.db.scalar(TestModel.select(fn.COUNT(TestModel.id)))
        self.assertEqual(count, 20)

    async def test_update(self):
        record = await self.create_record('test1', 100)

        def update_record():
            r = TestModel.get(TestModel.name == 'test1')
            r.value = 999
            r.save()

            r = TestModel.get(TestModel.name == 'test1')
            return r.value

        new_value = await self.db.run(update_record)
        self.assertEqual(new_value, 999)

    async def test_delete(self):
        for i in range(20):
            await self.create_record(f'item{i}', i * 10)

        def delete_query():
            return TestModel.delete().where(TestModel.value < 50).execute()

        await self.db.run(delete_query)
        self.assertEqual(await self.count_records(), 15)

    async def test_bulk_insert(self):
        def bulk_insert():
            with self.db.atomic():
                for i in range(100):
                    TestModel.create(name=f'bulk{i}', value=i)

        await self.db.run(bulk_insert)
        self.assertEqual(await self.count_records(), 100)


class TestBulkOperations(BaseDatabaseTestCase):
    async def test_bulk_create(self):
        records = [TestModel(name=f'bulk{i}', value=i) for i in range(100)]

        await self.db.run(TestModel.bulk_create, records, batch_size=25)
        self.assertEqual(await self.count_records(), 100)

    async def test_bulk_update(self):
        for i in range(50):
            await self.create_record(f'item{i}', i)

        def bulk_update():
            return (TestModel
                    .update(value=TestModel.value + 1000)
                    .where(TestModel.value < 25)
                    .execute())

        await self.db.run(bulk_update)

        def check():
            results = list(TestModel.select().where(TestModel.value >= 1000))
            return len(results)

        self.assertEqual(await self.db.run(check), 25)

    async def test_insert_many(self):
        def insert():
            data = [{'name': f'item{i}', 'value': i} for i in range(100)]
            return TestModel.insert_many(data).execute()

        await self.db.run(insert)
        self.assertEqual(await self.count_records(), 100)


class TestConcurrency(BaseDatabaseTestCase):
    async def test_concurrent_reads_writes(self):
        # Create initial data
        for i in range(10):
            await self.create_record(f'init{i}', i)

        async def writer(start_id):
            async with self.db:
                def write():
                    for i in range(5):
                        TestModel.create(
                            name=f'writer{start_id}-{i}',
                            value=start_id * 100 + i)
                await self.db.run(write)

        async def reader():
            async with self.db:
                return await self.db.run(lambda: len(list(TestModel.select())))

        # Run concurrent operations
        write_tasks = [writer(i) for i in range(3)]
        read_tasks = [reader() for i in range(3)]

        await asyncio.gather(*write_tasks)
        read_results = await asyncio.gather(*read_tasks)

        # All readers should get results
        self.assertTrue(all(r >= 10 for r in read_results))

        # Verify all writes completed
        self.assertEqual(await self.count_records(), 10 + 15)

    async def test_isolated_connections_per_task(self):
        async def task_worker(task_id):
            async with self.db:
                conn_before = self.db._state.conn
                await self.create_record(f'task{task_id}', task_id)
                conn_after = self.db._state.conn
                return conn_before is conn_after

        results = await asyncio.gather(*[task_worker(i) for i in range(5)])

        # Each task should use same connection throughout
        self.assertTrue(all(results))
        self.assertEqual(await self.count_records(), 5)

    async def test_many_concurrent_tasks(self):
        async def small_task(task_id):
            async with self.db:
                await self.create_record(f'task{task_id}', task_id)

        await asyncio.gather(*[small_task(i) for i in range(50)])
        self.assertEqual(await self.count_records(), 50)


class TestConnectionPool(BaseDatabaseTestCase):
    async def test_pool_initialization(self):
        db = AsyncSqliteDatabase(self.db.database)
        self.assertIsNone(db._pool)

        await db.aconnect()
        self.assertIsNotNone(db._pool)

        await db.aclose()
        await db.close_pool()

    async def test_multiple_close_safe(self):
        await self.db.aclose()
        await self.db.aclose()  # Should not error

        await self.db.aconnect()  # Can reconnect

    async def test_reconnect_after_pool_close(self):
        await self.create_record('first', 1)
        await self.db.aclose()
        await self.db.close_pool()

        self.assertIsNone(self.db._pool)

        # Reconnect and verify data persists
        async with self.db:
            self.assertEqual(await self.count_records(), 1)

        self.assertIsNotNone(self.db._pool)

    async def test_connection_reuse_within_task(self):
        await self.db.aconnect()
        first_conn = self.db._state.conn

        await self.create_record('test1', 1)
        second_conn = self.db._state.conn

        await self.create_record('test2', 2)
        third_conn = self.db._state.conn

        # All operations use same connection
        self.assertIs(first_conn, second_conn)
        self.assertIs(second_conn, third_conn)


class TestErrorHandling(BaseDatabaseTestCase):
    async def test_syntax_error_recovery(self):
        with self.assertRaises(Exception):
            await self.db.aexecute_sql('INVALID SQL')

        await self.create_record('after_error', 1)
        self.assertEqual(await self.count_records(), 1)

    async def test_constraint_violation_recovery(self):
        await self.db.aexecute_sql('CREATE TABLE unique_test ('
                                   'id INTEGER PRIMARY KEY,'
                                   'unique_value TEXT UNIQUE)')

        await self.db.aexecute_sql(
            'INSERT INTO unique_test (unique_value) VALUES (?)', ('unique',))

        with self.assertRaises(IntegrityError):
            await self.db.aexecute_sql(
                'INSERT INTO unique_test (unique_value) VALUES (?)', ('unique',))

        await self.db.aexecute_sql(
            'INSERT INTO unique_test (unique_value) VALUES (?)', ('different',))

    async def test_concurrent_errors(self):
        errors_caught = []
        successes = []

        async def task_that_may_fail(task_id):
            async with self.db:
                try:
                    def work():
                        TestModel.create(name=f'task{task_id}', value=task_id)
                        if task_id % 2 == 0:
                            raise ValueError(f'Task {task_id} fails')
                    await self.db.run(work)
                    successes.append(task_id)
                except ValueError:
                    errors_caught.append(task_id)

        await asyncio.gather(*[task_that_may_fail(i) for i in range(10)])

        self.assertEqual(sorted(errors_caught), [0, 2, 4, 6, 8])
        self.assertEqual(sorted(successes), [1, 3, 5, 7, 9])
        self.assertEqual(await self.count_records(), 10)

    async def test_exception_in_context_manager(self):
        try:
            async with self.db:
                raise RuntimeError('Test exception')
        except RuntimeError:
            pass

        # State should be cleaned up
        self.assertTrue(self.db._state.closed)

        # Can reconnect
        async with self.db:
            await self.create_record('after_error', 1)


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    db_path = None
    models = [TestModel, User, Tweet]

    def get_database(self):
        with tempfile.NamedTemporaryFile(delete=False) as db_file:
            self.db_path = db_file.name
        return AsyncSqliteDatabase(self.db_path)

    def tearDown(self):
        if self.db_path and os.path.exists(self.db_path):
            os.unlink(self.db_path)

    async def asyncSetUp(self):
        try:
            self.db = self.get_database()
            await self.db.aconnect()
            await self.db.aclose()
        except Exception as exc:
            self.skipTest(f'Cannot connect: {exc}')

        for model in self.models:
            model._meta.set_database(self.db)
        async with self.db:
            await self.db.adrop_tables(self.models)
            await self.db.acreate_tables(self.models)

    async def asyncTearDown(self):
        async with self.db:
            await self.db.adrop_tables(self.models)
        await self.db.close_pool()

    async def create_record(self, name='test', value=1):
        return await self.db.run(TestModel.create, name=name, value=value)

    async def count_records(self):
        return await self.db.run(TestModel.select().count)

    async def test_basic_crud(self):
        # Create
        record = await self.create_record('testx', value=2)
        self.assertEqual(record.name, 'testx')

        # Read
        fetched = await self.db.run(TestModel.get, TestModel.name == 'testx')
        self.assertEqual(fetched.value, 2)

        # Update
        def update():
            r = TestModel.get(TestModel.id == record.id)
            r.value = 100
            r.save()

            r = TestModel.get(TestModel.id == record.id)
            return r

        updated = await self.db.run(update)
        self.assertEqual(updated.value, 100)

        # Delete
        await self.db.run(TestModel.delete().where(TestModel.id == record.id).execute)
        count = await self.db.run(TestModel.select().count)
        self.assertEqual(count, 0)

    async def test_foreign_keys(self):
        users = [User(username=f'u{i}') for i in range(3)]
        await self.db.run(User.bulk_create, users)
        self.assertEqual(await self.db.run(User.select().count), 3)
        users = await self.db.list(User.select())

        async with self.db.atomic():
            for user in users:
                for i in range(2):
                    t = await self.db.run(Tweet.create, user=user,
                                          message=f'{user.username}-{i}')

        self.assertEqual(await self.db.run(Tweet.select().count), 6)

        query = Tweet.select().where(Tweet.message == 'u0-0')
        tweet = await self.db.get(query)

        # Resolving a foreign key must be done inside a greenlet context!
        self.assertEqual(await self.db.run(lambda: tweet.user.username), 'u0')

        # Selecting relations allows it to work.
        query = (Tweet.select(Tweet, User)
                 .join(User)
                 .where(Tweet.message == 'u0-0'))
        tweet = await self.db.get(query)
        self.assertEqual(tweet.user.username, 'u0')

        # Resolving related items must be done inside a greenlet.
        user = await self.db.get(User.select().where(User.username == 'u2'))
        tweets = await self.db.list(user.tweets.order_by(Tweet.id))
        self.assertEqual([t.message for t in tweets], ['u2-0', 'u2-1'])

        # Prefetch allows us to do it in one go:
        users = User.select().order_by(User.username)
        tweets = Tweet.select().order_by(Tweet.message)
        user_tweets = await self.db.run(prefetch, users, tweets)
        accum = [('u0', ['u0-0', 'u0-1']),
                 ('u1', ['u1-0', 'u1-1']),
                 ('u2', ['u2-0', 'u2-1'])]
        self.assertEqual([(u.username, [t.message for t in u.tweets])
                          for u in users], accum)

    async def test_concurrent_tasks(self):
        async def task_worker(task_id):
            async with self.db:
                for i in range(5):
                    await self.create_record(
                        f'task{task_id}_record{i}',
                        task_id * 100 + i)

        await asyncio.gather(*[task_worker(i) for i in range(10)])
        count = await self.db.run(TestModel.select().count)
        self.assertEqual(count, 50)

    async def test_transactions(self):
        # Successful transaction
        def successful_tx():
            with self.db.atomic():
                TestModel.create(name='tx1', value=1)
                TestModel.create(name='tx2', value=2)

        await self.db.run(successful_tx)
        self.assertEqual(await self.count_records(), 2)

        # Failed transaction
        def failed_tx():
            with self.db.atomic():
                TestModel.create(name='tx3', value=3)
                raise ValueError('fail')

        with self.assertRaises(ValueError):
            await self.db.run(failed_tx)

        # Mixed tx.
        async with self.db.atomic():
            await self.create_record('tx4')
            try:
                async with self.db.atomic():
                    await self.create_record('tx5')
                    self.assertEqual(await self.count_records(), 4)
                    raise ValueError('fail')
            except ValueError:
                pass
            self.assertEqual(await self.count_records(), 3)

        self.assertEqual(await self.count_records(), 3)


@unittest.skipUnless(asyncpg, 'asyncpg not installed')
class TestPostgresqlIntegration(TestIntegration):
    def get_database(self):
        return AsyncPostgresqlDatabase('peewee_test', **PSQL_PARAMS)

    async def test_placeholder_conversion(self):
        def insert_with_placeholders():
            return self.db.execute_sql(
                'INSERT INTO testmodel (name, value) VALUES (%s, %s)',
                ('placeholder_test', 999))

        await self.db.run(insert_with_placeholders)

        def query_with_placeholders():
            result = self.db.execute_sql(
                'SELECT * FROM testmodel WHERE name = %s',
                ('placeholder_test',))
            return result.fetchone()

        row = await self.db.run(query_with_placeholders)
        self.assertIsNotNone(row)
        self.assertEqual(row['name'], 'placeholder_test')
        self.assertEqual(row['value'], 999)


@unittest.skipUnless(aiomysql, 'aiomysql not installed')
class TestMySQLIntegration(TestIntegration):
    def get_database(self):
        return AsyncMySQLDatabase('peewee_test', **MYSQL_PARAMS)


if __name__ == '__main__':
    unittest.main()
