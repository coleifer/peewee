import datetime

from peewee import *
from playhouse.tests.base import TestModel


class User(TestModel):
    username = CharField()

    class Meta:
        db_table = 'users'

    def prepared(self):
        self.foo = self.username

    @classmethod
    def create_users(cls, n):
        for i in range(n):
            cls.create(username='u%d' % (i + 1))


class Blog(TestModel):
    user = ForeignKeyField(User)
    title = CharField(max_length=25)
    content = TextField(default='')
    pub_date = DateTimeField(null=True)
    pk = PrimaryKeyField()

    def __unicode__(self):
        return '%s: %s' % (self.user.username, self.title)

    def prepared(self):
        self.foo = self.title


class Comment(TestModel):
    blog = ForeignKeyField(Blog, related_name='comments')
    comment = CharField()


class Relationship(TestModel):
    from_user = ForeignKeyField(User, related_name='relationships')
    to_user = ForeignKeyField(User, related_name='related_to')


class NullModel(TestModel):
    char_field = CharField(null=True)
    text_field = TextField(null=True)
    datetime_field = DateTimeField(null=True)
    int_field = IntegerField(null=True)
    float_field = FloatField(null=True)
    decimal_field1 = DecimalField(null=True)
    decimal_field2 = DecimalField(decimal_places=2, null=True)
    double_field = DoubleField(null=True)
    bigint_field = BigIntegerField(null=True)
    date_field = DateField(null=True)
    time_field = TimeField(null=True)
    boolean_field = BooleanField(null=True)


class UniqueModel(TestModel):
    name = CharField(unique=True)


class OrderedModel(TestModel):
    title = CharField()
    created = DateTimeField(default=datetime.datetime.now)

    class Meta:
        order_by = ('-created',)


class Category(TestModel):
    parent = ForeignKeyField('self', related_name='children', null=True)
    name = CharField()


class UserCategory(TestModel):
    user = ForeignKeyField(User)
    category = ForeignKeyField(Category)


class NonIntModel(TestModel):
    pk = CharField(primary_key=True)
    data = CharField()


class NonIntRelModel(TestModel):
    non_int_model = ForeignKeyField(NonIntModel, related_name='nr')


class DBUser(TestModel):
    user_id = PrimaryKeyField(db_column='db_user_id')
    username = CharField(db_column='db_username')


class DBBlog(TestModel):
    blog_id = PrimaryKeyField(db_column='db_blog_id')
    title = CharField(db_column='db_title')
    user = ForeignKeyField(DBUser, db_column='db_user')


class SeqModelA(TestModel):
    id = IntegerField(primary_key=True, sequence='just_testing_seq')
    num = IntegerField()


class SeqModelB(TestModel):
    id = IntegerField(primary_key=True, sequence='just_testing_seq')
    other_num = IntegerField()

class AutoIncrementModel(TestModel):
    id = PrimaryKeyField()
    expected = IntegerField()

class MultiIndexModel(TestModel):
    f1 = CharField()
    f2 = CharField()
    f3 = CharField()

    class Meta:
        indexes = (
            (('f1', 'f2'), True),
            (('f2', 'f3'), False),
        )


class BlogTwo(Blog):
    title = TextField()
    extra_field = CharField()


class Parent(TestModel):
    data = CharField()


class Child(TestModel):
    parent = ForeignKeyField(Parent)
    data = CharField(default='')


class Orphan(TestModel):
    parent = ForeignKeyField(Parent, null=True)
    data = CharField(default='')


class ChildPet(TestModel):
    child = ForeignKeyField(Child)
    data = CharField(default='')


class OrphanPet(TestModel):
    orphan = ForeignKeyField(Orphan)
    data = CharField(default='')


class ChildNullableData(TestModel):
    child = ForeignKeyField(Child, null=True)
    data = CharField()


class CSVField(TextField):
    def db_value(self, value):
        if value:
            return ','.join(value)
        return value or ''

    def python_value(self, value):
        return value.split(',') if value else []


class CSVRow(TestModel):
    data = CSVField()


class BlobModel(TestModel):
    data = BlobField()


class Job(TestModel):
    name = CharField()


class JobExecutionRecord(TestModel):
    job = ForeignKeyField(Job, primary_key=True)
    status = CharField()


class TestModelA(TestModel):
    field = CharField(primary_key=True)
    data = CharField()


class TestModelB(TestModel):
    field = CharField(primary_key=True)
    data = CharField()


class TestModelC(TestModel):
    field = CharField(primary_key=True)
    data = CharField()


class Post(TestModel):
    title = CharField()


class Tag(TestModel):
    tag = CharField()


class TagPostThrough(TestModel):
    tag = ForeignKeyField(Tag, related_name='posts')
    post = ForeignKeyField(Post, related_name='tags')

    class Meta:
        primary_key = CompositeKey('tag', 'post')


class TagPostThroughAlt(TestModel):
    tag = ForeignKeyField(Tag, related_name='posts_alt')
    post = ForeignKeyField(Post, related_name='tags_alt')


class Manufacturer(TestModel):
    name = CharField()


class CompositeKeyModel(TestModel):
    f1 = CharField()
    f2 = IntegerField()
    f3 = FloatField()

    class Meta:
        primary_key = CompositeKey('f1', 'f2')


class UserThing(TestModel):
    thing = CharField()
    user = ForeignKeyField(User, related_name='things')

    class Meta:
        primary_key = CompositeKey('thing', 'user')


class Component(TestModel):
    name = CharField()
    manufacturer = ForeignKeyField(Manufacturer, null=True)


class Computer(TestModel):
    hard_drive = ForeignKeyField(Component, related_name='c1')
    memory = ForeignKeyField(Component, related_name='c2')
    processor = ForeignKeyField(Component, related_name='c3')


class CheckModel(TestModel):
    value = IntegerField(constraints=[Check('value > 0')])


# Deferred foreign keys.
SnippetProxy = Proxy()

class Language(TestModel):
    name = CharField()
    selected_snippet = ForeignKeyField(SnippetProxy, null=True)


class Snippet(TestModel):
    code = TextField()
    language = ForeignKeyField(Language, related_name='snippets')

SnippetProxy.initialize(Snippet)


class _UpperField(CharField):
    def python_value(self, value):
        return value.upper() if value else value


class UpperUser(TestModel):
    username = _UpperField()
    class Meta:
        db_table = User._meta.db_table


class Package(TestModel):
    barcode = CharField(unique=True)


class PackageItem(TestModel):
    title = CharField()
    package = ForeignKeyField(
        Package,
        related_name='items',
        to_field=Package.barcode)


class PGSchema(TestModel):
    data = CharField()
    class Meta:
        schema = 'huey'


class UpperCharField(CharField):
    def coerce(self, value):
        value = super(UpperCharField, self).coerce(value)
        if value:
            value = value.upper()
        return value


class UpperModel(TestModel):
    data = UpperCharField()

class CommentCategory(TestModel):
    category = ForeignKeyField(Category)
    comment = ForeignKeyField(Comment)
    sort_order = IntegerField(default=0)

    class Meta:
        primary_key = CompositeKey('comment', 'category')

class BlogData(TestModel):
    blog = ForeignKeyField(Blog)


MODELS = [
    User,
    Blog,
    Comment,
    Relationship,
    NullModel,
    UniqueModel,
    OrderedModel,
    Category,
    UserCategory,
    NonIntModel,
    NonIntRelModel,
    DBUser,
    DBBlog,
    SeqModelA,
    SeqModelB,
    MultiIndexModel,
    BlogTwo,
    Parent,
    Child,
    Orphan,
    ChildPet,
    OrphanPet,
    BlobModel,
    Job,
    JobExecutionRecord,
    TestModelA,
    TestModelB,
    TestModelC,
    Tag,
    Post,
    TagPostThrough,
    TagPostThroughAlt,
    Language,
    Snippet,
    Manufacturer,
    CompositeKeyModel,
    UserThing,
    Component,
    Computer,
    CheckModel,
    Package,
    PackageItem,
    PGSchema,
    UpperModel,
    CommentCategory,
    BlogData,
]
