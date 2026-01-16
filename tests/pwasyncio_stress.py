import asyncio
import os
import random
import sys
import time
import tracemalloc
from playhouse.pwasyncio import *


def make_db_params(key):
    params = {}
    env_vars = [(part, 'PEEWEE_%s_%s' % (key, part.upper()))
                for part in ('host', 'port', 'user', 'password')]
    for param, env_var in env_vars:
        value = os.environ.get(env_var)
        if value:
            params[param] = int(value) if param == 'port' else value
    return params

PSQL_PARAMS = make_db_params('PSQL')


class User(Model):
    name = TextField()
    email = TextField()

    class Meta:
        table_name = 'stress_test_users'

async def worker_task(db, task_id, num_operations=10):
    User._meta.set_database(db)

    try:
        await db.aconnect()

        for i in range(num_operations):
            op = random.choice(['create', 'read', 'update', 'delete', 'transaction'])
            name = 'User-%s-%s' % (task_id, i)
            email = 'user%s_%s@test.com' % (task_id, i)

            if op == 'create':
                await db.run(User.create, name=name, email=email)

            elif op == 'read':
                users = await db.list(User.select().limit(5))

            elif op == 'update':
                users = await db.list(User.select().limit(1))
                if users:
                    user = users[0]
                    user.name = 'Updated-%s-%s' % (task_id, i)
                    await db.run(user.save)

            elif op == 'delete':
                users = await db.list(User.select().limit(1))
                if users:
                    await db.run(users[0].delete_instance)

            elif op == 'transaction':
                async with db.atomic():
                    await db.run(User.create,
                               name='TX-%s-%s' % (task_id, i),
                               email='tx%s_%s@test.com' % (task_id, i))
                    try:
                        async with db.atomic():
                            await db.run(User.create,
                                         name='Nested-%s-%s' % (task_id, i),
                                         email='nested%s_%s@test.com' % (task_id, i))
                            if random.random() < 0.3:  # 30% chance of rollback
                                raise ValueError('Intentional rollback')
                    except ValueError:
                        pass

            # Small random delay to simulate real work
            if random.random() < 0.1:
                await asyncio.sleep(0.001)

        # Close connection
        await db.aclose()
        return "Task %s completed successfully" % task_id

    except Exception as exc:
        print(exc)
        return "Task %s failed: %s" % (task_id, exc)


async def stress_test(db, num_tasks=100, ops_per_task=10):
    print('STRESS TEST: %s tasks x %s ops/task' % (num_tasks, ops_per_task))
    print('Database: %s' % db)

    User._meta.database = db

    # Setup
    print('Setting up database...')
    async with db:
        await db.acreate_tables([User])

    # Track memory
    tracemalloc.start()
    initial_memory = tracemalloc.get_traced_memory()[0]

    # Run stress test
    print('Spawning %s concurrent tasks...' % num_tasks)
    start_time = time.time()

    tasks = [worker_task(db, i, ops_per_task) for i in range(num_tasks)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

    # Check memory
    final_memory = tracemalloc.get_traced_memory()[0]
    memory_delta = (final_memory - initial_memory) / 1024 / 1024  # MB
    tracemalloc.stop()

    successful = sum(1 for r in results if isinstance(r, str) and 'completed' in r)
    failed = len(results) - successful

    # Check final state
    async with db:
        total_users = await db.run(User.select().count)

    # Cleanup dead tasks
    cleaned = db._state.cleanup_dead_tasks()

    # Report
    throughput = (num_tasks * ops_per_task) / elapsed
    print('RESULTS')
    print('Duration: %0.2fs' % elapsed)
    print('Throughput: %0.1f ops/sec' % throughput)
    print('Successful tasks: %s/%s' % (successful, num_tasks))
    print('Failed tasks: %s/%s' % (failed, num_tasks))
    print('Total users in DB: %s' % total_users)
    print('Memory delta: %0.2f MB' % memory_delta)
    print('Dead tasks cleaned: %s' % cleaned)
    print('Remaining task states: %s' % len(db._state._state_storage))
    print('-' * 60)

    # Cleanup
    async with db:
        await db.adrop_tables([User])
    await db.close_pool()

    return successful == num_tasks


async def test_connection_isolation():
    print('CONNECTION ISOLATION TEST')

    db = AsyncPostgresqlDatabase('peewee_test', pool_size=5, **PSQL_PARAMS)
    User._meta.database = db

    async with db:
        await db.acreate_tables([User])

    async def task_with_transaction(task_id, delay):
        """Each task holds a transaction for a specific duration."""
        await db.aconnect()

        async with db.atomic():
            # Create a user
            await db.run(User.create, name='Task-%s' % task_id, email='t%s@test.com' % task_id)

            # Hold the transaction
            await asyncio.sleep(delay)

            # Verify we can still see our own changes
            users = await db.run(list, User.select().where(User.name == 'Task-%s' % task_id))
            assert len(users) == 1, 'Task %s lost its data!' % task_id

        await db.aclose()
        return 'Task %s isolated correctly' % task_id

    # Spawn multiple tasks that will overlap in time
    tasks = [
        task_with_transaction(0, 0.1),
        task_with_transaction(1, 0.2),
        task_with_transaction(2, 0.15),
        task_with_transaction(3, 0.05),
    ]

    results = await asyncio.gather(*tasks)
    print('All tasks completed:')
    for r in results:
        print('  - %s' % r)

    # Cleanup
    async with db:
        final_count = await db.run(User.select().count)
        print('Final user count: %s (expected 4)' % final_count)
        await db.adrop_tables([User])
    await db.close_pool()

    print('-' * 60)
    return True


async def test_pool_exhaustion():
    print('POOL EXHAUSTION TEST')

    # Create a small pool
    db = AsyncPostgresqlDatabase('peewee_test', pool_size=3, pool_min_size=1,
                                 **PSQL_PARAMS)
    User._meta.database = db

    async with db:
        await db.acreate_tables([User])

    async def slow_task(task_id):
        await db.run(db.connect)
        await db.run(User.create, name='Slow-%s' % task_id, email='s%s@test.com' % task_id)
        await asyncio.sleep(0.5)  # Hold connection
        await db.run(db.close)
        return task_id

    print('Spawning 10 tasks with pool_size=3...')
    print('(Tasks should queue and complete successfully)')

    start = time.time()
    tasks = [slow_task(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start

    print('All %s tasks completed in %.2fs' % (len(results), elapsed))
    print('Expected ~1.5s (3 batches of parallel execution)')

    # Cleanup
    async with db:
        await db.adrop_tables([User])
    await db.close_pool()

    print('-' * 60)
    return True


async def main():
    print('ASYNC PEEWEE STRESS TEST SUITE')
    print('-' * 60)

    # Test 1: Basic stress test with many tasks
    db = AsyncPostgresqlDatabase('peewee_test', pool_size=20, **PSQL_PARAMS)
    success1 = await stress_test(db, num_tasks=100, ops_per_task=20)

    # Test 2: Even more tasks with smaller pool
    db2 = AsyncPostgresqlDatabase('peewee_test', pool_size=5, **PSQL_PARAMS)
    success2 = await stress_test(db2, num_tasks=200, ops_per_task=10)

    # Test 3: Even smaller pool.
    db3 = AsyncPostgresqlDatabase('peewee_test', pool_size=3, **PSQL_PARAMS)
    success3 = await stress_test(db2, num_tasks=100, ops_per_task=20)

    ## Test 3: Connection isolation
    success4 = await test_connection_isolation()

    ## Test 4: Pool exhaustion
    success5 = await test_pool_exhaustion()

    # Final report
    print('=' * 60)
    print('Stress Test 1 (100 tasks): %s' % 'OK' if success1 else 'FAIL')
    print('Stress Test 2 (200 tasks): %s' % 'OK' if success2 else 'FAIL')
    print('Stress Test 3 (100 tasks): %s' % 'OK' if success3 else 'FAIL')
    print('Isolation Test: %s' % 'OK' if success4 else 'FAIL')
    print('Pool Exhaustion Test: %s' % 'OK' if success5 else 'FAIL')
    print('=' * 60)

    if all([success1, success2, success3, success4, success5]):
        print('Success')
        return 0
    else:
        print('Failed')
        return 1


if __name__ == '__main__':
    rc = asyncio.run(main())
    sys.exit(rc)
