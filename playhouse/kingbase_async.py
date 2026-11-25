import asyncio
import contextvars
import functools
import inspect
import json
import logging
import re

from peewee import DataError as PeeweeDataError
from peewee import DatabaseError as PeeweeDatabaseError
from peewee import ImproperlyConfigured
from peewee import IntegrityError as PeeweeIntegrityError
from peewee import OperationalError as PeeweeOperationalError
from peewee import ProgrammingError as PeeweeProgrammingError

from playhouse.kingbase_native import KingbaseMySQLDatabase
from playhouse.kingbase_native import KingbaseOracleDatabase
from playhouse.kingbase_native import KingbaseSQLServerDatabase


try:
    import asyncpg
    from asyncpg.exceptions import ConnectionDoesNotExistError
    from asyncpg.exceptions import ConnectionFailureError
    from asyncpg.exceptions import DataError as AsyncpgDataError
    from asyncpg.exceptions import IntegrityConstraintViolationError
    from asyncpg.exceptions import InterfaceError as AsyncpgInterfaceError
    from asyncpg.exceptions import PostgresConnectionError
    from asyncpg.exceptions import PostgresError
    from asyncpg.exceptions import SyntaxOrAccessError
except ImportError:
    asyncpg = None


logger = logging.getLogger(__name__)


def _require_asyncpg_kes():
    """Reject the upstream asyncpg package before attempting a connection.

    asyncpg-kes deliberately exports the same ``asyncpg`` module name, but
    only its ``connect()`` accepts the ``kes_mode`` argument passed by the
    Kingbase pool. Checking that capability also works for an editable source
    installation, where distribution metadata may be unavailable.
    """
    if asyncpg is None:
        raise ImproperlyConfigured(
            'Kingbase async connections require asyncpg-kes.')
    try:
        parameters = inspect.signature(asyncpg.connect).parameters
    except (AttributeError, TypeError, ValueError):
        parameters = {}
    if 'kes_mode' not in parameters:
        raise ImproperlyConfigured(
            'Kingbase async connections require asyncpg-kes; the imported '
            'asyncpg driver does not support kes_mode.')
    return asyncpg

#: Public database classes for the three compatibility modes.
#: AST 方言、Connection Codec、事务 helper 均为内部实现细节，不对外导出。
__all__ = [
    'AsyncKingbaseMySQLDatabase',
    'AsyncKingbaseOracleDatabase',
    'AsyncKingbaseSQLServerDatabase',
]

_DOLLAR_QUOTE = re.compile(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$')


def async_exception_wrapper(func):
    """异步执行出口的异常映射装饰器。

    将 asyncpg / asyncpg-kes 的原生异常精确转换为 Peewee 标准异常谱系，
    使上层业务的 ``try...except peewee.IntegrityError`` 等写法在同步与
    异步两条链路上行为完全一致。转换时以 ``raise ... from exc`` 保留
    原始异常链，数据库原始报错信息不丢失。

    映射规则（自上而下优先命中）：
        IntegrityConstraintViolationError（含 Unique/NotNull/FK 等子类）
            -> peewee.IntegrityError
        SyntaxOrAccessError（含语法错误、权限不足等子类）
            -> peewee.ProgrammingError
        DataError（含数值/字符串截断等子类）
            -> peewee.DataError
        连接类异常（PostgresConnectionError 及子类、ConnectionDoesNotExist、
        ConnectionFailure、InterfaceError）
            -> peewee.OperationalError
        PostgresError（其余数据库侧异常，兜底）
            -> peewee.DatabaseError
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if asyncpg is None:
            raise ImproperlyConfigured(
                'asyncpg (asyncpg-kes) is not installed')
        try:
            return await func(*args, **kwargs)
        except IntegrityConstraintViolationError as exc:
            raise PeeweeIntegrityError(str(exc)) from exc
        except SyntaxOrAccessError as exc:
            raise PeeweeProgrammingError(str(exc)) from exc
        except AsyncpgDataError as exc:
            raise PeeweeDataError(str(exc)) from exc
        except (PostgresConnectionError,
                ConnectionDoesNotExistError,
                ConnectionFailureError,
                AsyncpgInterfaceError) as exc:
            raise PeeweeOperationalError(str(exc)) from exc
        except PostgresError as exc:
            raise PeeweeDatabaseError(str(exc)) from exc
    return wrapper


class AsyncKingbaseDatabaseMixin(object):
    """封装 asyncpg 连接池与 %s -> $1 占位符转换的异步金仓基类。

    设计目标与 playhouse.pwasyncio.AsyncDatabaseMixin 对齐：
      - 延迟创建 asyncpg 连接池；
      - 通过 `kes_mode` 显式告知 asyncpg-kes 驱动当前金仓兼容模式；
      - 所有底层执行路径统一做占位符转换，方言 AST 保持零侵入；
      - 连接池与锁全部绑定当前运行的事件循环，天然适配 ASGI 多 Worker 场景。
    """

    kes_mode = None

    def __init__(self, database, **kwargs):
        self._pool_size = kwargs.pop('pool_size', 10)
        self._pool_min_size = kwargs.pop('pool_min_size', 1)
        self._acquire_timeout = kwargs.pop('acquire_timeout', 10)
        # 物理建连超时：透传给 asyncpg.create_pool(**connect_kwargs)，
        # 约束单个新连接的 TCP/握手时长；与 acquire_timeout（池排队等待）
        # 是两个独立概念。显式传入 0/None 可回退驱动默认值。
        self._connect_timeout = kwargs.pop('connect_timeout', 10)
        self._pool = None
        self._pool_loop = None
        # 每个数据库对象独立保存事务连接。ContextVar 的值会向子任务传播，
        # 但另一个数据库对象不能因此误用本实例的连接。
        self._async_tx_conn = contextvars.ContextVar(
            'kingbase_async_conn_%x' % id(self), default=None)
        # 锁不能在 __init__ 里创建：那样会绑定模块加载时的默认事件循环，
        # 在 ASGI Worker 的新循环中使用会抛 attached to a different loop。
        self._pool_lock = None
        super(AsyncKingbaseDatabaseMixin, self).__init__(database, **kwargs)

    async def connect_async(self):
        """ASGI lifespan 启动钩子：强制唤醒并等待连接池就绪。

        典型用法（FastAPI）：

            @asynccontextmanager
            async def lifespan(app):
                await db.connect_async()
                yield
                await db.close_async()
        """
        await self.acreate_pool()
        return self

    async def close_async(self):
        """ASGI lifespan 清理钩子：优雅关闭连接池。"""
        await self.aclose_pool()

    async def aclose_pool(self):
        """关闭连接池（保留旧名，测试基座仍在调用）。"""
        await self._close_pool_quietly()

    async def _close_pool_quietly(self):
        pool, self._pool = self._pool, None
        self._pool_loop = None
        if pool is not None:
            try:
                await pool.close()
            except Exception:
                logger.warning('Error closing asyncpg pool', exc_info=True)

    async def _init_connection(self, conn):
        """asyncpg 连接初始化回调：注册 JSON / JSONB 编解码。

        保证 Python 的 dict / list 与数据库端 JSON、JSONB 类型透明互转，
        让 ``aget / alist`` 取回的结果保持原生 Python 类型。
        """
        if self.kes_mode == 'sqlserver':
            # V9R4C19 returns sys.int for ordinary SELECT/IDENTITY values.
            # Without a scalar codec asyncpg's type-introspection query
            # recursively introspects its own sys.int result.
            await conn.set_type_codec(
                'int', encoder=str, decoder=int,
                schema='sys', format='text')
        await conn.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog')
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog')

    async def _setup_connection(self, conn):
        # The pool resets session settings on release, so this must run on
        # every acquire rather than only once in the init callback.
        if (self.kes_mode == 'oracle' and
                self.preserve_empty_strings):
            await conn.execute('SET ora_input_emptystr_isnull TO off')
        elif self.kes_mode == 'sqlserver':
            await conn.execute('SET arithabort ON')

    async def acreate_pool(self):
        driver = _require_asyncpg_kes()
        loop = asyncio.get_running_loop()

        # 跨事件循环：旧池归属于其他循环，先静默关闭再按需重建。
        if self._pool is not None and self._pool_loop is not loop:
            await self._close_pool_quietly()

        if self._pool is None:
            # 懒加载且循环安全的锁：在当前运行的事件循环中现场创建；
            # 若已有锁但归属于其他循环，则重建，避免 attached to a different loop。
            lock = self._pool_lock
            if lock is None or getattr(lock, '_loop', None) not in (None, loop):
                lock = self._pool_lock = asyncio.Lock()
            async with lock:
                if self._pool is None:
                    connect_kwargs = {}
                    if self._connect_timeout:
                        connect_kwargs['timeout'] = self._connect_timeout
                    self._pool = await driver.create_pool(
                        host=self.connect_params.get('host'),
                        port=int(self.connect_params.get('port', 54321)),
                        user=self.connect_params.get('user'),
                        password=self.connect_params.get('password', ''),
                        database=self.database,
                        min_size=self._pool_min_size,
                        max_size=self._pool_size,
                        kes_mode=self.kes_mode,
                        init=self._init_connection,
                        setup=self._setup_connection,
                        **connect_kwargs,
                    )
                    self._pool_loop = loop
        return self._pool

    @classmethod
    def _translate_placeholders(cls, sql, params=None, kes_mode=None):
        """仅转换 SQL 代码区的 DB-API 占位符，保留字面量与注释。

        直接调用时可不传 params，用于查看转换结果；执行入口会传入实际
        参数并校验数量，避免把原生 SQL 中的非绑定文本误当作参数。
        注释语法按目标模式识别：MySQL 模式中的 # 可紧邻代码；
        #>、#>>、#- 则是可执行运算符，不开启行注释。
        """
        if kes_mode is None:
            kes_mode = cls.kes_mode

        output = []
        index = count = 0
        native_placeholders = False
        length = len(sql)
        paired = {'[': ']', '{': '}', '(': ')', '<': '>'}
        while index < length:
            char = sql[index]

            # Oracle q'[...]' 字面量也可能包含 %s。
            if (char in 'qQ' and index + 2 < length and
                    sql[index + 1] == "'" and
                    (index == 0 or not (sql[index - 1].isalnum() or
                                        sql[index - 1] == '_'))):
                delimiter = sql[index + 2]
                closing = paired.get(delimiter, delimiter) + "'"
                end = sql.find(closing, index + 3)
                if end < 0:
                    raise ValueError('Unterminated Oracle quoted SQL literal.')
                end += len(closing)
                output.append(sql[index:end])
                index = end
                continue

            if char in ("'", '"', '`'):
                start = index
                quote = char
                # Backslash-escaped quotes occur in MySQL-compatible raw SQL;
                # treating them as quoted content is safer than rewriting a
                # literal %s as a bound placeholder.
                escaped = quote == "'"
                index += 1
                while index < length:
                    if escaped and sql[index] == '\\':
                        index += 2
                    elif sql[index] == quote:
                        if index + 1 < length and sql[index + 1] == quote:
                            index += 2
                        else:
                            index += 1
                            break
                    else:
                        index += 1
                else:
                    raise ValueError('Unterminated SQL quoted value or identifier.')
                output.append(sql[start:index])
                continue

            if (sql.startswith('--', index) or
                    (kes_mode == 'mysql' and char == '#' and
                     not sql.startswith(('#>', '#-'), index))):
                end = sql.find('\n', index)
                if end < 0:
                    output.append(sql[index:])
                    break
                output.append(sql[index:end + 1])
                index = end + 1
                continue

            if sql.startswith('/*', index):
                start = index
                index += 2
                depth = 1
                while index < length and depth:
                    if sql.startswith('/*', index):
                        depth += 1
                        index += 2
                    elif sql.startswith('*/', index):
                        depth -= 1
                        index += 2
                    else:
                        index += 1
                if depth:
                    raise ValueError('Unterminated SQL block comment.')
                output.append(sql[start:index])
                continue

            if char == '$':
                match = _DOLLAR_QUOTE.match(sql, index)
                if match:
                    delimiter = match.group()
                    end = sql.find(delimiter, match.end())
                    if end < 0:
                        raise ValueError('Unterminated dollar-quoted SQL literal.')
                    end += len(delimiter)
                    output.append(sql[index:end])
                    index = end
                    continue
                if index + 1 < length and sql[index + 1].isdigit():
                    end = index + 2
                    while end < length and sql[end].isdigit():
                        end += 1
                    native_placeholders = True
                    output.append(sql[index:end])
                    index = end
                    continue

            if sql.startswith('%%', index):
                output.append('%%')
                index += 2
            elif sql.startswith('%s', index):
                count += 1
                output.append('$%d' % count)
                index += 2
            else:
                output.append(char)
                index += 1

        if count and native_placeholders:
            raise ValueError('Mixed SQL placeholder styles are not supported.')
        if params is not None and not native_placeholders and count != len(params):
            raise ValueError('SQL placeholder count does not match bound parameters.')
        return ''.join(output)

    @staticmethod
    def _resolve_sql(sql, params):
        """同时接受原生 SQL 字符串与 Peewee Query 对象。"""
        if hasattr(sql, 'sql'):
            sql, params = sql.sql()
        return sql, params

    async def _conn(self):
        """返回 (连接, 是否需要在用完归还)。

        优先使用本数据库对象 ContextVar 中的活动连接——事务内的深层
        Service 调用（甚至 create_task 派生的子协程）都能自动感知并复用，
        不会再向池中申请新连接；上下文为空时才走常规池申请。

        池排队等待受 ``acquire_timeout`` 约束；等待超时转换为
        ``peewee.OperationalError`` 并保留异常链。不捕获
        ``CancelledError``，任务取消语义不受影响。
        """
        ctx_conn = self._async_tx_conn.get()
        if ctx_conn is not None:
            return ctx_conn, False
        pool = await self.acreate_pool()
        try:
            conn = await pool.acquire(timeout=self._acquire_timeout)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise PeeweeOperationalError(
                'pool acquire timeout after %ss' % self._acquire_timeout
            ) from exc
        return conn, True

    async def _release(self, conn):
        pool = await self.acreate_pool()
        await pool.release(conn)

    @async_exception_wrapper
    async def aexecute(self, sql, params=None):
        """执行写语句并返回执行结果。

        纯异步非阻塞接口：底层直连 asyncpg-kes，从连接池申请连接执行。

        :param sql: 原生 SQL 字符串，或任意 Peewee Query 对象（自动提取 SQL）。
        :param params: 查询参数元组/列表；传 Query 对象时该参数可省略。
        :return: asyncpg 命令执行结果（命令状态字符串等）。
        """
        sql, params = self._resolve_sql(sql, params)
        conn, release = await self._conn()
        try:
            translated = self._translate_placeholders(
                sql, params or (), kes_mode=self.kes_mode)
            if release:
                async with conn.transaction():
                    return await conn.execute(translated, *(params or ()))
            return await conn.execute(translated, *(params or ()))
        finally:
            if release:
                await self._release(conn)

    @async_exception_wrapper
    async def afetchrow(self, sql, params=None):
        """执行查询并取回结果集的单行（Record 或 None）。

        纯异步非阻塞接口：底层直连 asyncpg-kes。

        :param sql: 原生 SQL 字符串，或任意 Peewee Query 对象。
        :param params: 查询参数元组/列表；传 Query 对象时该参数可省略。
        :return: asyncpg ``Record``；无结果时返回 ``None``。
        """
        sql, params = self._resolve_sql(sql, params)
        conn, release = await self._conn()
        try:
            translated = self._translate_placeholders(
                sql, params or (), kes_mode=self.kes_mode)
            if release:
                async with conn.transaction():
                    return await conn.fetchrow(translated, *(params or ()))
            return await conn.fetchrow(translated, *(params or ()))
        finally:
            if release:
                await self._release(conn)

    @async_exception_wrapper
    async def afetchval(self, sql, params=None):
        """执行查询并取回结果集首行首列的单值。

        纯异步非阻塞接口：底层直连 asyncpg-kes。

        :param sql: 原生 SQL 字符串，或任意 Peewee Query 对象。
        :param params: 查询参数元组/列表；传 Query 对象时该参数可省略。
        :return: 单列标量值；无结果时返回 ``None``。
        """
        sql, params = self._resolve_sql(sql, params)
        conn, release = await self._conn()
        try:
            translated = self._translate_placeholders(
                sql, params or (), kes_mode=self.kes_mode)
            if release:
                async with conn.transaction():
                    return await conn.fetchval(translated, *(params or ()))
            return await conn.fetchval(translated, *(params or ()))
        finally:
            if release:
                await self._release(conn)

    def atransaction(self, **kwargs):
        """异步事务上下文管理器：``async with db.atransaction():``

        纯异步接口，底层直连 asyncpg-kes。进入后利用本实例的 ``ContextVar`` 把活动
        连接写入上下文，事务内所有执行入口（含深层 Service 调用、
        ``asyncio.create_task`` 派生的子协程）都会**无感级联**复用该连接。

        因此开发者在事务内部调用 ``acreate / alist / aexecute`` 等 CRUD 时，
        **绝对不需要显式传递 conn 参数**；退出时按是否异常 commit / rollback。
        """
        return _AsyncKingbaseTransaction(self, **kwargs)

    #: 与 pwasyncio 保持一致，atomic 是 transaction 的别名。
    aatomic = atransaction

    @staticmethod
    def _row_to_model(query, row):
        """按字段列名把 asyncpg Record 组装成模型实例。"""
        model = query.model
        meta = model._meta
        data = dict(row)
        values = {}
        for name, field in meta.fields.items():
            col = field.column_name
            if col in data:
                values[name] = data[col]
        return model(**values)

    async def aget(self, query):
        """执行查询并返回单条模型实例；无结果抛 ``DoesNotExist``。

        纯异步非阻塞接口：底层直连 asyncpg-kes，经 Record + 字段映射构造实例。
        """
        row = await self.afetchrow(query)
        if row is None:
            raise query.model.DoesNotExist
        return self._row_to_model(query, row)

    @async_exception_wrapper
    async def alist(self, query):
        """执行查询并返回模型实例列表。

        纯异步非阻塞接口：底层直连 asyncpg-kes。
        """
        sql, params = query.sql()
        conn, release = await self._conn()
        try:
            translated = self._translate_placeholders(
                sql, params or (), kes_mode=self.kes_mode)
            if release:
                async with conn.transaction():
                    rows = await conn.fetch(translated, *(params or ()))
            else:
                rows = await conn.fetch(translated, *(params or ()))
        finally:
            if release:
                await self._release(conn)
        return [self._row_to_model(query, row) for row in rows]

    async def acount(self, query):
        """对给定的查询执行 ``SELECT COUNT(*)`` 并返回行数。

        纯异步非阻塞接口：底层直连 asyncpg-kes。
        """
        sql, params = query.sql()
        wrapped = 'SELECT COUNT(*) FROM (%s) AS _count' % sql
        return await self.afetchval(wrapped, params)

    async def aexists(self, query):
        """返回查询是否至少命中一行（布尔值）。

        纯异步非阻塞接口：底层直连 asyncpg-kes。
        """
        return await self.acount(query) > 0

    async def ainsert(self, query, returning=None):
        """执行 Insert 并通过 RETURNING 回填主键。

        纯异步非阻塞接口：底层直连 asyncpg-kes。

        Kingbase 三种兼容模式底层均为 PG 协议，显式 ``returning`` 即可取回主键；
        显式指定比依赖 ``returning_clause`` 标志更可控。

        :param query: Peewee ``Insert`` / ``ModelInsert`` 查询对象。
        :param returning: 回填的列（默认取模型主键）。
        :return: 回填的主键值；未指定 RETURNING 时返回 ``None``。
        """
        model = getattr(query, 'model', None)
        if returning is None and model is not None:
            returning = model._meta.primary_key
        if returning is not None:
            query = query.returning(returning)
        row = await self.afetchrow(query)
        if row is not None:
            return row[0]
        return None

    async def acreate(self, model, **kwargs):
        """创建模型实例、执行插入并回填主键；等价于 ``Model.create()``。

        纯异步非阻塞接口：底层直连 asyncpg-kes。返回的实例 ``id`` 已通过
        RETURNING 回填，可直接使用。
        """
        instance = model(**kwargs)
        pk_value = await self.ainsert(model.insert(**kwargs))
        if pk_value is not None:
            pk_field = model._meta.primary_key
            setattr(instance, pk_field.name, pk_value)
        return instance

    async def acreate_tables(self, models, **options):
        """提取建表 Context 的 query() 并通过异步池执行"""
        for model in models:
            # 1. 提取并执行 CREATE TABLE
            ctx = model._schema._create_table(**options)
            sql, params = ctx.query()
            await self.aexecute(sql, params)

            # 2. 提取并执行关联的 CREATE INDEX
            safe = options.get('safe', False)
            for index_ctx in model._schema._create_indexes(safe=safe):
                idx_sql, idx_params = index_ctx.query()
                await self.aexecute(idx_sql, idx_params)

    async def adrop_tables(self, models, **options):
        """提取删表 Context 的 query() 并通过异步池执行"""
        for model in reversed(list(models)):
            ctx = model._schema._drop_table(**options)
            sql, params = ctx.query()
            await self.aexecute(sql, params)


class _AsyncKingbaseTransaction(object):
    """asyncpg 事务上下文：``async with db.atransaction():``

    进入时从连接池取出一条连接并开启事务，随后把该连接写入
    所属数据库对象的 ContextVar，事务内所有执行入口（含深层调用
    与 create_task 派生子协程）自动复用；退出时按是否异常 commit / rollback，
    先 reset ContextVar 再归还连接，避免连接被其他上下文复用后串用。
    """

    def __init__(self, db, **kwargs):
        self.db = db
        self._conn = None
        self._tx = None
        self._token = None

    async def __aenter__(self):
        conn, release = await self.db._conn()
        if not release:
            raise RuntimeError('Nested async transactions are not supported yet.')
        self._conn = conn
        self._tx = self._conn.transaction()
        await self._tx.start()
        self._token = self.db._async_tx_conn.set(conn)
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                await self._tx.rollback()
            else:
                await self._tx.commit()
        finally:
            if self._token is not None:
                self.db._async_tx_conn.reset(self._token)
                self._token = None
            await self.db._release(self._conn)
            self._conn = None


class AsyncKingbaseMySQLDatabase(AsyncKingbaseDatabaseMixin,
                                 KingbaseMySQLDatabase):
    """金仓 MySQL 兼容模式的异步数据库封装。"""

    kes_mode = 'mysql'

    def __init__(self, database, **kwargs):
        kwargs.setdefault('port', 54321)
        super(AsyncKingbaseMySQLDatabase, self).__init__(database, **kwargs)


class AsyncKingbaseOracleDatabase(AsyncKingbaseDatabaseMixin,
                                  KingbaseOracleDatabase):
    """金仓 Oracle 兼容模式的异步数据库封装。"""

    kes_mode = 'oracle'

    def __init__(self, database, **kwargs):
        kwargs.setdefault('port', 54322)
        super(AsyncKingbaseOracleDatabase, self).__init__(database, **kwargs)


class AsyncKingbaseSQLServerDatabase(AsyncKingbaseDatabaseMixin,
                                     KingbaseSQLServerDatabase):
    """KingbaseES SQL Server mode using the asyncpg-kes SQL Server driver."""

    kes_mode = 'sqlserver'

    def __init__(self, database, **kwargs):
        kwargs.setdefault('port', 54325)
        super(AsyncKingbaseSQLServerDatabase, self).__init__(database, **kwargs)
