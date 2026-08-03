"""
Migration runner built on the playhouse.migrate helpers.

Migrations are plain python scripts in a directory, applied in numeric
order and recorded by name in a history table. Each script defines
``up(migrator, db)`` and (optionally) ``down(migrator, db)``:

    # migrations/0002_add_karma.py
    from peewee import *

    def up(migrator, db):
        migrator.migrate(
            migrator.add_column('user', 'karma', IntegerField(default=0)))

    def down(migrator, db):
        migrator.migrate(migrator.drop_column('user', 'karma'))

Nothing is introspected at runtime or auto-detected. New tables need no special
support: declare the model inline (a frozen copy, deliberately independent of
the application models) and call ``db.create_tables()`` from ``up()``.

Set ``atomic = False`` at module scope to disable transaction wrapping.
"""
import datetime
import glob
import importlib.util
import logging
import os
import re
import sys

from peewee import *
from peewee import sort_models
from playhouse.migrate import SchemaMigrator
from playhouse.migrate import make_index_name

__all__ = ['MigrationError', 'Runner', 'run', 'template']

logger = logging.getLogger('peewee.migrations')

TEMPLATE = '''\
"""%s"""
from peewee import *


def up(migrator, db):
    # migrator.migrate(
    #     migrator.add_column('tbl', 'col', TextField(default='')))
    pass


# def down(migrator, db):
#     pass
'''


class MigrationError(Exception):
    pass


def _key(name):
    match = re.match(r'\d+', name)
    return (int(match.group()) if match else -1, name)


class Runner(object):
    def __init__(self, database, directory='migrations',
                 table_name='schema_migration'):
        self.database = database
        self.directory = directory
        self.migrator = SchemaMigrator.from_database(database)
        history_table = table_name

        class History(database.Model):
            name = CharField(unique=True)
            applied = DateTimeField(default=datetime.datetime.now)
            class Meta:
                legacy_table_names = False
                table_name = history_table

        self.History = History

    def migrations(self):
        paths = glob.glob(os.path.join(self.directory, '[0-9]*.py'))
        names = {os.path.basename(path)[:-3]: path for path in paths}
        return dict(sorted(names.items(), key=lambda kv: _key(kv[0])))

    def applied(self):
        if not self.History.table_exists():
            return {}
        return {h.name: h.applied for h in self.History.select()}

    def status(self):
        applied = self.applied()
        migrations = self.migrations()
        accum = []
        for name in migrations:
            accum.append((name, applied.get(name)))
        # Rows recorded as applied whose files are gone.
        for name in sorted(set(applied) - set(migrations), key=_key):
            accum.append((name, applied[name]))
        return accum

    def up(self, target=None, fake=False):
        """
        Apply all pending migrations in order, or, given a target, stop
        after applying it. Returns the applied names.
        """
        migrations = self.migrations()
        if target is not None and target not in migrations:
            raise MigrationError('unknown migration "%s".' % target)

        applied = self.applied()
        plan = []
        for name, path in migrations.items():
            if name not in applied:
                module = self._load(name, path)
                if getattr(module, 'up', None) is None:
                    raise MigrationError('%s does not define up().' % name)
                plan.append((name, module))
            if name == target:
                break

        self.History.create_table()

        accum = []
        for name, module in plan:
            self._run(name, module, 'up', fake=fake)
            accum.append(name)

        return accum

    def down(self, target=None):
        """
        Revert the most recently-applied migration, or, given a target,
        every applied migration back through the target.
        """
        applied = self.applied()
        if target is not None and target not in applied:
            raise MigrationError('"%s" is not an applied migration.' % target)

        migrations = self.migrations()
        plan = []
        for name in sorted(applied, key=_key, reverse=True):
            if name not in migrations:
                raise MigrationError('cannot revert "%s": migration file '
                                     'is missing.' % name)
            module = self._load(name, migrations[name])
            if getattr(module, 'down', None) is None:
                raise MigrationError('%s does not define down().' % name)

            plan.append((name, module))
            if target is None or (name == target):
                break

        accum = []
        for name, module in plan:
            self._run(name, module, 'down')
            accum.append(name)

        return accum

    def fake(self, target=None):
        """
        Record pending migrations as applied without running them,
        stopping after the target if given. Returns the recorded names.
        """
        return self.up(target, fake=True)

    def create(self, name, body=None):
        """Write a numbered skeleton migration file. Returns its path."""
        os.makedirs(self.directory, exist_ok=True)
        idx = max((_key(n)[0] for n in self.migrations()), default=0) + 1
        slug = re.sub(r'[^\w]+', '_', name.strip()).strip('_').lower()
        path = os.path.join(self.directory,
                            '%04d_%s.py' % (idx, slug or 'migration'))
        with open(path, 'w') as fh:
            fh.write(body or (TEMPLATE % name))
        return path

    def _load(self, name, path):
        # Execute the file at the exact path, bypassing sys.path and the
        # sys.modules cache (migration names collide across projects).
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run(self, name, module, direction, fake=False):
        # The plan was validated as it was built. Run it blind.
        logger.info('%s: %s%s', direction, name, ' [FAKE]' if fake else '')
        if fake:
            self.History.create(name=name)
            return

        with self.migrator.migration_context(getattr(module, 'atomic', True)):
            getattr(module, direction)(self.migrator, self.database)
            if direction == 'up':
                self.History.create(name=name)
            else:
                (self.History.delete()
                 .where(self.History.name == name)
                 .execute())


def run(database, directory='migrations', **kwargs):
    return Runner(database, directory, **kwargs).up()


def _flag_args(field, todos):
    args = []
    if field.primary_key and not isinstance(field, AutoField):
        args.append('primary_key=True')
    if field.unique:
        args.append('unique=True')
    elif field.index and not isinstance(field, ForeignKeyField):
        args.append('index=True')
    if field.null:
        args.append('null=True')

    if isinstance(field, CharField) and field.max_length != 255:
        args.append('max_length=%r' % field.max_length)
    elif isinstance(field, DecimalField):
        if field.max_digits != 10:
            args.append('max_digits=%r' % field.max_digits)
        if field.decimal_places != 5:
            args.append('decimal_places=%r' % field.decimal_places)

    # Basic `default=` handling. This is trivial on purpose.
    if field.default is not None:
        if isinstance(field.default, (str, int, float, bool)):
            args.append('default=%r' % field.default)
        else:
            todos.append('%s: default %r must be added by hand'
                         % (field.name, field.default))

    return args


def _is_implicit_id(field):
    return (type(field) is AutoField and field.name == 'id' and
            field.column_name == 'id')


def _field_source(field, imports, todos, targets=None, unbound=False):
    cls = type(field)
    if cls.__module__ != 'peewee':
        imports.add('from %s import %s' % (cls.__module__, cls.__name__))

    if isinstance(field, ForeignKeyField):
        rel = field.rel_model
        ref = targets[rel]
        args = [ref]
        if unbound or field.rel_field is not rel._meta.primary_key:
            # Destination field needs to be explicitly specified when the field
            # is unbound (add_column calls) or if FK is not to the rel's PK.
            args.append('field=%s.%s' % (ref, field.rel_field.name))

        args.extend(_flag_args(field, todos))

        default_colname = (field.name if field.name.endswith('_id')
                           else field.name + '_id')
        if field.column_name != default_colname:
            args.append('column_name=%r' % field.column_name)
        if field.on_delete: args.append('on_delete=%r' % field.on_delete)
        if field.on_update: args.append('on_update=%r' % field.on_update)
    else:
        args = _flag_args(field, todos)
        if field.column_name != field.name:
            args.append('column_name=%r' % field.column_name)

    return '%s(%s)' % (cls.__name__, ', '.join(args))


def _model_source(model, imports, todos, targets):
    meta = model._meta
    refs = dict(targets)
    refs[model] = "'self'"
    lines = ['class %s(Model):' % model.__name__]
    for field in meta.sorted_fields:
        if _is_implicit_id(field):
            continue
        lines.append('    %s = %s' % (
            field.name,
            _field_source(field, imports, todos, refs)))
    lines.append('    class Meta:')
    lines.append('        database = db')
    lines.append('        table_name = %r' % meta.table_name)
    if meta.schema:
        lines.append('        schema = %r' % meta.schema)
    pk = meta.primary_key
    if isinstance(pk, CompositeKey):
        lines.append('        primary_key = CompositeKey(%s)' %
                     ', '.join(repr(f) for f in pk.field_names))
    elif not pk:
        lines.append('        primary_key = False')
    plain = []
    for index in (meta.indexes or ()):
        if isinstance(index, (list, tuple)):
            columns, unique = index
            plain.append((tuple(columns), unique))
        else:
            todos.append('%s: index %s must be added by hand'
                         % (meta.table_name,
                            getattr(index, '_name', None) or repr(index)))
    if plain:
        lines.append('        indexes = %r' % (tuple(plain),))
    return lines


def _stub_source(model, fields, imports):
    # A frozen stand-in for an existing table: its name plus whichever
    # referenced columns are not the implicit id.
    meta = model._meta
    lines = ['class %s(Model):' % model.__name__]
    for field in fields:
        lines.append('    %s = %s' % (field.name,
                                      _field_source(field, imports, [])))
    lines.append('    class Meta:')
    lines.append('        database = db')
    lines.append('        table_name = %r' % meta.table_name)
    if meta.schema:
        lines.append('        schema = %r' % meta.schema)
    lines.append('')
    return lines


def _add_index_source(idx):
    return 'migrator.migrate(migrator.add_index(%r, %r%s))' % (
        idx.table,
        idx.columns,
        ', unique=True' if idx.unique else '')


def _block(fn, lines):
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return 'def %s(migrator, db):\n    pass' % fn
    return 'def %s(migrator, db):\n%s' % (fn, '\n'.join(
        '    %s' % line if line else '' for line in lines))


def template(diff):
    """
    Render a playhouse.schema_diff.SchemaDiff as a migration-file body.
    Fully-determined changes render as runnable code. Foreign keys
    reference a model created in the file, 'self', or a frozen stub of
    the target table. Anything else needing a definition is flagged
    with a TODO comment.
    """
    todos, imports = [], set()

    # Ensure all FK reference targets exist, either as classes or stubs.
    fks = []
    for model in diff.create_tables:
        fks.extend(f for f in model._meta.sorted_fields
                   if isinstance(f, ForeignKeyField) and
                   f.rel_model is not model)
    fks.extend(f for f in diff.add_columns
               if isinstance(f, ForeignKeyField))

    created = set(diff.create_tables)
    stubs = {}  # Existing fk target -> referenced fields, by name.
    for field in fks:
        rel = field.rel_model
        if rel in created:
            continue
        fields = stubs.setdefault(rel, {})
        if not _is_implicit_id(field.rel_field):
            fields[field.rel_field.name] = field.rel_field
    targets = {model: model.__name__ for model in created | set(stubs)}

    plan = []
    for model in sorted(stubs, key=lambda m: m.__name__):
        fields = sorted(stubs[model].values(), key=lambda f: f._sort_key)
        plan.append((_stub_source(model, fields, imports), []))

    for model in diff.create_tables:
        up = _model_source(model, imports, todos, targets)
        up.extend(['db.create_tables([%s])' % model.__name__, ''])

        meta = model._meta
        down = 'migrator.migrate(migrator.drop_table(%r%s))' % (
            meta.table_name,
            ', schema=%r' % meta.schema if meta.schema else '')
        plan.append((up, [down]))

    # Index drops go first: a unique flip or a rename re-uses the old
    # index name, and sqlite refuses to drop an indexed column.
    dropped = set(diff.drop_columns)
    for idx in diff.drop_indexes:
        up = ['migrator.migrate(migrator.drop_index(%r, %r))' %
              (idx.table, idx.name)]
        down = []
        if idx.columns is None:
            todos.append('%s: dropped index %s (partial/expression) cannot '
                         'be restored by down()' % (idx.table, idx.name))
        elif any((idx.table, column) in dropped for column in idx.columns):
            todos.append('%s: dropped index %s cannot be restored by '
                         'down() (column dropped)' % (idx.table, idx.name))
        else:
            down.append(_add_index_source(idx))
        plan.append((up, down))

    qualified = set()
    for field in diff.add_columns:
        meta = field.model._meta
        if meta.schema:
            qualified.add(meta.table_name)

        source = _field_source(field, imports, todos, targets, unbound=True)
        if not field.null and field.default is None:
            todos.append('%s.%s: not-null column needs a default or '
                         'allow_not_null backfill' %
                         (meta.table_name, field.column_name))
        plan.append((
            ['migrator.migrate(migrator.add_column(%r, %r, %s))' %
             (meta.table_name, field.column_name, source)],
            ['migrator.migrate(migrator.drop_column(%r, %r))' %
             (meta.table_name, field.column_name)]))

    # add_column() creates the index for an index=True/unique=True field
    # itself, while `down()` drops the index before the column.
    auto_indexed = set((f.model._meta.table_name, (f.column_name,),
                        bool(f.unique))
                       for f in diff.add_columns if f.index or f.unique)
    for idx in diff.add_indexes:
        if idx.columns is None:
            todos.append('%s: create index %s (partial/expression, details '
                         'not detected)' % (idx.table, idx.name))
            continue
        up = []
        if (idx.table, idx.columns, idx.unique) not in auto_indexed:
            up.append(_add_index_source(idx))
        down = ['migrator.migrate(migrator.drop_index(%r, %r))' %
                (idx.table, make_index_name(idx.table, idx.columns))]
        plan.append((up, down))

    for table, name in diff.drop_columns:
        plan.append((['migrator.migrate(migrator.drop_column(%r, %r))' %
                      (table, name)], []))
        todos.append('%s.%s: dropped column cannot be restored by down()' %
                     (table, name))

    if qualified:
        todos.append('schema-qualified tables (%s): column/index '
                     'operations are emitted unqualified. Qualify by hand' %
                     ', '.join(sorted(qualified)))

    up, down = [], []
    for u, _ in plan:
        up.extend(u)
    for _, d in reversed(plan):
        down.extend(d)

    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    out = ['# Generated from a schema diff on %s.' % ts,
           'from peewee import *']

    out.extend(sorted(imports))
    out.append('')
    out.extend('# TODO: %s' % todo for todo in todos)
    if todos:
        out.append('')
    out.append(_block('up', up))
    out.append('')
    out.append('')
    out.append(_block('down', down))
    return '\n'.join(out) + '\n'


def _is_model(obj):
    return isinstance(obj, type) and issubclass(obj, Model)


def _cwd_import(path):
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    return importlib.import_module(path)


def _resolve_models(spec):
    attr = None
    if ':' in spec:
        spec, attr = spec.split(':', 1)
    module = _cwd_import(spec)
    if attr:
        obj = getattr(module, attr, None)
        if obj is None:
            raise MigrationError('"%s" not found in module "%s".'
                                 % (attr, spec))
        if _is_model(obj):
            return [obj], []
        try:
            models = list(obj)
        except TypeError:
            raise MigrationError('"%s:%s" must name a Model or a list '
                                 'of Models.' % (spec, attr))
        for model in models:
            if not _is_model(model):
                raise MigrationError('"%s:%s" must name a Model or a list '
                                     'of Models.' % (spec, attr))
        return models, []
    models, skipped = [], []
    for value in vars(module).values():
        if _is_model(value) and value is not Model and \
           value.__module__ == module.__name__:
            fields = value._meta.sorted_fields
            if len(fields) == 1 and _is_implicit_id(fields[0]) and \
               not value._meta.indexes:
                skipped.append(value.__name__)
            else:
                models.append(value)
    if not models:
        raise MigrationError('no models found in module "%s".' % spec)
    return models, skipped


def _resolve_database(spec):
    if '://' in spec:
        from playhouse.db_url import connect
        try:
            database = connect(spec)
        except (RuntimeError, ValueError) as exc:  # Malformed url.
            raise MigrationError(str(exc))
        try:
            database.connect()
            database.close()
        except Exception as exc:
            raise MigrationError('cannot connect to "%s": %s' % (spec, exc))
        return database
    if os.path.isfile(spec):
        return SqliteDatabase(spec)
    if '.' not in spec:
        raise MigrationError('database must be given as a db url, a sqlite '
                             'filename, or a dotted path to a Database '
                             'instance.')
    module_path, attr = spec.rsplit('.', 1)
    try:
        module = _cwd_import(module_path)
    except ModuleNotFoundError as exc:
        # Errors importing the named module get a clean one-liner. Errors
        # raised by the module itself propagate with their traceback.
        if exc.name and (module_path == exc.name or
                         module_path.startswith(exc.name + '.')):
            raise MigrationError('"%s" is not a db url, sqlite file, or '
                                 'importable module path.' % spec)
        raise
    obj = getattr(module, attr, None)
    if obj is None:
        raise MigrationError('"%s" not found in module "%s".'
                             % (attr, module_path))
    if callable(obj) and not isinstance(obj, Database):
        obj = obj()
    if isinstance(obj, Proxy):
        if obj.obj is None:
            raise MigrationError('"%s" is an uninitialized database proxy.'
                                 % spec)
        obj = obj.obj
    if not isinstance(obj, Database):
        raise MigrationError('"%s" did not resolve to a Database.' % spec)
    if not obj.database:
        raise MigrationError('"%s" is a deferred database. Initialize it, '
                             'or point at one that is.' % spec)
    # "app.db" reads as a filename; say which interpretation won (a file
    # by that name, once created, would take precedence).
    if re.match(r'[^.]+\.(db|sqlite3?)$', spec):
        sys.stderr.write('note: no file "%s" exists; resolved as module '
                         '"%s", attribute "%s".\n'
                         % (spec, module_path, attr))
    return obj


def _resolve_diff(database, spec):
    from playhouse.schema_diff import SchemaDiff, diff_models
    models, skipped = _resolve_models(spec)
    for name in skipped:
        sys.stderr.write('skipped: %s (no fields)\n' % name)
    if database is None:  # initial: assume an empty database.
        return SchemaDiff(sort_models(models), [], [], [], [])
    try:
        return diff_models(database, models)
    except ValueError as exc:
        raise MigrationError(str(exc))


def main(argv=None):
    import argparse
    import traceback
    prog = os.path.basename(sys.argv[0] or '')
    if not prog.startswith('pwmigrate'):
        prog = 'python -m playhouse.migrations'
    parser = argparse.ArgumentParser(
        prog=prog, description='peewee migration runner')
    parser.add_argument('database', help='dotted path to a Database '
                        'instance (e.g. myapp.settings.db), db url (e.g. '
                        'postgres:///app), or path to a sqlite file')
    parser.add_argument('command',
                        choices=('status', 'up', 'down', 'initial', 'create',
                                 'fake', 'diff'))
    parser.add_argument('target', nargs='?',
                        help='migration name: stop after it (up), revert '
                        'back through it (down), record through it (fake), '
                        'or describe it (create). For initial and diff, '
                        'the models module')
    parser.add_argument('-d', '--directory', default='migrations',
                        help='migrations directory (default: migrations)')
    parser.add_argument('-t', '--table', default='schema_migration',
                        help='history table name')
    parser.add_argument('-m', '--models', metavar='MODULE',
                        help='models module ("app.models" or '
                        '"app.models:MODELS"). With create, generate the '
                        'migration from the schema diff')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='echo SQL as it executes')
    args = parser.parse_args(argv)

    if args.verbose:
        peewee_logger = logging.getLogger('peewee')
        peewee_logger.addHandler(logging.StreamHandler())
        peewee_logger.setLevel(logging.DEBUG)
    if args.command == 'create' and not args.target:
        parser.error('create requires a migration name.')
    if args.command in ('initial', 'diff') and \
       not (args.target or args.models):
        parser.error('%s requires a models module.' % args.command)

    database = None
    try:
        database = _resolve_database(args.database)
        runner = Runner(database, args.directory, args.table)
        if args.command == 'initial':
            if runner.migrations():
                raise MigrationError('migrations already exist in "%s".'
                                     % args.directory)
            diff = _resolve_diff(None, args.target or args.models)
            print(runner.create('initial', body=template(diff)))
        elif args.command == 'create':
            if args.models:
                diff = _resolve_diff(database, args.models)
                if not diff:
                    print('schema matches models. Nothing to generate.')
                    return 0
                print(runner.create(args.target, body=template(diff)))
            else:
                print(runner.create(args.target))
        elif args.command == 'diff':
            diff = _resolve_diff(database, args.target or args.models)
            print(diff if diff else 'schema matches models.')
        elif args.command == 'status':
            files = runner.migrations()
            rows = runner.status()
            for name, applied in rows:
                if not applied:
                    marker = ' '
                elif name in files:
                    marker = 'x'
                else:
                    marker = '?'
                line = '[%s] %s' % (marker, name)
                if applied:
                    line += '  ' + applied.strftime('%Y-%m-%d %H:%M:%S')
                print(line)
            # Exit 1 when pending, so status can gate a deploy.
            if any(not applied for _, applied in rows):
                return 1
        else:
            if args.command == 'up':
                names, verb = runner.up(args.target), 'applied'
            elif args.command == 'down':
                names, verb = runner.down(args.target), 'reverted'
            else:
                names, verb = runner.fake(args.target), 'faked'
            for name in names:
                print('%s: %s' % (verb, name))
            if not names:
                print('nothing to do.')
    except (MigrationError, DatabaseError, InterfaceError,
            ImproperlyConfigured) as exc:
        if args.verbose:
            traceback.print_exc()
        sys.stderr.write('error: %s\n' % exc)
        return 2
    finally:
        if database is not None:
            database.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
