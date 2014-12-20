class TransactionTestCase(ModelTestCase):
    requires = [User, Blog]

    def tearDown(self):
        super(TransactionTestCase, self).tearDown()
        test_db.set_autocommit(True)

    def test_autocommit(self):
        if database_class is BerkeleyDatabase:
            if TEST_VERBOSITY > 0:
                print_('Skipping `test_autocommit` for berkeleydb.')
            return

        test_db.set_autocommit(False)
        test_db.begin()

        u1 = User.create(username='u1')
        u2 = User.create(username='u2')

        # open up a new connection to the database, it won't register any blogs
        # as being created
        new_db = self.new_connection()
        res = new_db.execute_sql('select count(*) from users;')
        self.assertEqual(res.fetchone()[0], 0)

        # commit our blog inserts
        test_db.commit()

        # now the blogs are query-able from another connection
        res = new_db.execute_sql('select count(*) from users;')
        self.assertEqual(res.fetchone()[0], 2)

    def test_transactions(self):
        def transaction_generator():
            with test_db.transaction():
                User.create(username='u1')
                yield
                User.create(username='u2')

        gen = transaction_generator()
        next(gen)

        conn2 = self.new_connection()
        res = conn2.execute_sql('select count(*) from users;').fetchone()
        self.assertEqual(res[0], 0)

        self.assertEqual(User.select().count(), 1)

        # Consume the rest of the generator.
        for _ in gen:
            pass

        self.assertEqual(User.select().count(), 2)
        res = conn2.execute_sql('select count(*) from users;').fetchone()
        self.assertEqual(res[0], 2)

    def test_manual_commit_rollback(self):
        def assertUsers(expected):
            query = User.select(User.username).order_by(User.username)
            self.assertEqual(
                [username for username, in query.tuples()],
                expected)

        with test_db.transaction() as txn:
            User.create(username='charlie')
            txn.commit()
            User.create(username='huey')
            txn.rollback()

        assertUsers(['charlie'])

        with test_db.transaction() as txn:
            User.create(username='huey')
            txn.rollback()
            User.create(username='zaizee')

        assertUsers(['charlie', 'zaizee'])

    def test_transaction_decorator(self):
        @test_db.transaction()
        def create_user(username):
            User.create(username=username)

        create_user('charlie')
        self.assertEqual(User.select().count(), 1)

    def test_commit_on_success(self):
        self.assertTrue(test_db.get_autocommit())

        @test_db.commit_on_success
        def will_fail():
            User.create(username='u1')
            Blog.create() # no blog, will raise an error

        self.assertRaises(IntegrityError, will_fail)
        self.assertEqual(User.select().count(), 0)
        self.assertEqual(Blog.select().count(), 0)

        @test_db.commit_on_success
        def will_succeed():
            u = User.create(username='u1')
            Blog.create(title='b1', user=u)

        will_succeed()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

    def test_context_mgr(self):
        def do_will_fail():
            with test_db.transaction():
                User.create(username='u1')
                Blog.create() # no blog, will raise an error

        self.assertRaises(IntegrityError, do_will_fail)
        self.assertEqual(Blog.select().count(), 0)

        def do_will_succeed():
            with transaction(test_db):
                u = User.create(username='u1')
                Blog.create(title='b1', user=u)

        do_will_succeed()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

        def do_manual_rollback():
            with test_db.transaction() as txn:
                User.create(username='u2')
                txn.rollback()

        do_manual_rollback()
        self.assertEqual(User.select().count(), 1)
        self.assertEqual(Blog.select().count(), 1)

    def test_nesting_transactions(self):
        @test_db.commit_on_success
        def outer(should_fail=False):
            self.assertEqual(test_db.transaction_depth(), 1)
            User.create(username='outer')
            inner(should_fail)
            self.assertEqual(test_db.transaction_depth(), 1)

        @test_db.commit_on_success
        def inner(should_fail):
            self.assertEqual(test_db.transaction_depth(), 2)
            User.create(username='inner')
            if should_fail:
                raise ValueError('failing')

        self.assertRaises(ValueError, outer, should_fail=True)
        self.assertEqual(User.select().count(), 0)
        self.assertEqual(test_db.transaction_depth(), 0)

        outer(should_fail=False)
        self.assertEqual(User.select().count(), 2)
        self.assertEqual(test_db.transaction_depth(), 0)


class TestExecutionContext(ModelTestCase):
    requires = [User]

    def test_context_simple(self):
        with test_db.execution_context():
            User.create(username='charlie')
            self.assertEqual(test_db.execution_context_depth(), 1)
        self.assertEqual(test_db.execution_context_depth(), 0)

        with test_db.execution_context():
            self.assertTrue(
                User.select().where(User.username == 'charlie').exists())
            self.assertEqual(test_db.execution_context_depth(), 1)
        self.assertEqual(test_db.execution_context_depth(), 0)
        queries = self.queries()

    def test_context_ext(self):
        with test_db.execution_context():
            with test_db.execution_context() as inner_ctx:
                with test_db.execution_context():
                    User.create(username='huey')
                    self.assertEqual(test_db.execution_context_depth(), 3)

                conn = test_db.get_conn()
                self.assertEqual(conn, inner_ctx.connection)

                self.assertTrue(
                    User.select().where(User.username == 'huey').exists())

        self.assertEqual(test_db.execution_context_depth(), 0)

    def test_context_multithreaded(self):
        conn = test_db.get_conn()
        evt = threading.Event()
        evt2 = threading.Event()

        def create():
            with test_db.execution_context() as ctx:
                database = ctx.database
                self.assertEqual(database.execution_context_depth(), 1)
                evt2.set()
                evt.wait()
                self.assertNotEqual(conn, ctx.connection)
                User.create(username='huey')

        create_t = threading.Thread(target=create)
        create_t.daemon = True
        create_t.start()

        evt2.wait()
        self.assertEqual(test_db.execution_context_depth(), 0)
        evt.set()
        create_t.join()

        self.assertEqual(test_db.execution_context_depth(), 0)
        self.assertEqual(User.select().count(), 1)

    def test_context_concurrency(self):
        def create(i):
            with test_db.execution_context():
                with test_db.execution_context() as ctx:
                    User.create(username='u%s' % i)
                    self.assertEqual(ctx.database.execution_context_depth(), 2)

        threads = [threading.Thread(target=create, args=(i,))
                   for i in range(5)]
        for thread in threads:
            thread.start()
        [thread.join() for thread in threads]
        self.assertEqual(
            [user.username for user in User.select().order_by(User.username)],
            ['u0', 'u1', 'u2', 'u3', 'u4'])


class AutoRollbackTestCase(ModelTestCase):
    requires = [User, Blog]

    def setUp(self):
        test_db.autorollback = True
        super(AutoRollbackTestCase, self).setUp()

    def tearDown(self):
        test_db.autorollback = False
        test_db.set_autocommit(True)
        super(AutoRollbackTestCase, self).tearDown()

    def test_auto_rollback(self):
        # Exceptions are still raised.
        self.assertRaises(IntegrityError, Blog.create)

        # The transaction should have been automatically rolled-back, allowing
        # us to create new objects (in a new transaction).
        u = User.create(username='u')
        self.assertTrue(u.id)

        # No-op, the previous INSERT was already committed.
        test_db.rollback()

        # Ensure we can get our user back.
        u_db = User.get(User.username == 'u')
        self.assertEqual(u.id, u_db.id)

    def test_transaction_ctx_mgr(self):
        'Only auto-rollback when autocommit is enabled.'
        def create_error():
            self.assertRaises(IntegrityError, Blog.create)

        # autocommit is disabled in a transaction ctx manager.
        with test_db.transaction():
            # Error occurs, but exception is caught, leaving the current txn
            # in a bad state.
            create_error()

            try:
                create_error()
            except Exception as exc:
                # Subsequent call will raise an InternalError with postgres.
                self.assertTrue(isinstance(exc, InternalError))
            else:
                self.assertFalse(database_class is PostgresqlDatabase)

        # New transactions are not affected.
        self.test_auto_rollback()

    def test_manual(self):
        test_db.set_autocommit(False)

        # Will not be rolled back.
        self.assertRaises(IntegrityError, Blog.create)

        if database_class is PostgresqlDatabase:
            self.assertRaises(InternalError, User.create, username='u')

        test_db.rollback()
        u = User.create(username='u')
        test_db.commit()
        u_db = User.get(User.username == 'u')
        self.assertEqual(u.id, u_db.id)


if test_db.savepoints:
    class TestSavepoints(ModelTestCase):
        requires = [User]

        def _outer(self, fail_outer=False, fail_inner=False):
            with test_db.savepoint():
                User.create(username='outer')
                try:
                    self._inner(fail_inner)
                except ValueError:
                    pass
                if fail_outer:
                    raise ValueError

        def _inner(self, fail_inner):
            with test_db.savepoint():
                User.create(username='inner')
                if fail_inner:
                    raise ValueError('failing')

        def assertNames(self, expected):
            query = User.select().order_by(User.username)
            self.assertEqual([u.username for u in query], expected)

        def test_success(self):
            with test_db.transaction():
                self._outer()
                self.assertEqual(User.select().count(), 2)
            self.assertNames(['inner', 'outer'])

        def test_inner_failure(self):
            with test_db.transaction():
                self._outer(fail_inner=True)
                self.assertEqual(User.select().count(), 1)
            self.assertNames(['outer'])

        def test_outer_failure(self):
            # Because the outer savepoint is rolled back, we'll lose the
            # inner savepoint as well.
            with test_db.transaction():
                self.assertRaises(ValueError, self._outer, fail_outer=True)
                self.assertEqual(User.select().count(), 0)

        def test_failure(self):
            with test_db.transaction():
                self.assertRaises(
                    ValueError, self._outer, fail_outer=True, fail_inner=True)
                self.assertEqual(User.select().count(), 0)

    class TestAtomic(ModelTestCase):
        requires = [User, UniqueModel]

        def test_atomic(self):
            with test_db.atomic():
                User.create(username='u1')
                with test_db.atomic():
                    User.create(username='u2')
                    with test_db.atomic() as txn3:
                        User.create(username='u3')
                        txn3.rollback()

                    with test_db.atomic():
                        User.create(username='u4')

                with test_db.atomic() as txn5:
                    User.create(username='u5')
                    txn5.rollback()

                User.create(username='u6')

            query = User.select().order_by(User.username)
            self.assertEqual(
                [u.username for u in query],
                ['u1', 'u2', 'u4', 'u6'])

        def test_atomic_second_connection(self):
            def test_separate_conn(expected):
                new_db = self.new_connection()
                cursor = new_db.execute_sql('select username from users;')
                usernames = sorted(row[0] for row in cursor.fetchall())
                self.assertEqual(usernames, expected)
                new_db.close()

            with test_db.atomic():
                User.create(username='u1')
                test_separate_conn([])

                with test_db.atomic():
                    User.create(username='u2')

                with test_db.atomic() as tx3:
                    User.create(username='u3')
                    tx3.rollback()

                test_separate_conn([])

                users = User.select(User.username).order_by(User.username)
                self.assertEqual(
                    [user.username for user in users],
                    ['u1', 'u2'])

            users = User.select(User.username).order_by(User.username)
            self.assertEqual(
                [user.username for user in users],
                ['u1', 'u2'])

        def test_atomic_decorator(self):
            @test_db.atomic()
            def create_user(username):
                User.create(username=username)

            create_user('charlie')
            self.assertEqual(User.select().count(), 1)

        def test_atomic_decorator_nesting(self):
            @test_db.atomic()
            def create_unique(name):
                UniqueModel.create(name=name)

            @test_db.atomic()
            def create_both(username):
                User.create(username=username)
                try:
                    create_unique(username)
                except IntegrityError:
                    pass

            create_unique('huey')
            self.assertEqual(UniqueModel.select().count(), 1)

            create_both('charlie')
            self.assertEqual(User.select().count(), 1)
            self.assertEqual(UniqueModel.select().count(), 2)

            create_both('huey')
            self.assertEqual(User.select().count(), 2)
            self.assertEqual(UniqueModel.select().count(), 2)


elif TEST_VERBOSITY > 0:
    print_('Skipping "savepoint" tests')
