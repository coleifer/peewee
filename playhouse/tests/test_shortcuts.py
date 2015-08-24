from peewee import *
from peewee import Expression
from peewee import OP
from playhouse.hybrid import hybrid_method
from playhouse.hybrid import hybrid_property
from playhouse.shortcuts import *
from playhouse.test_utils import assert_query_count
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase


db = database_initializer.get_in_memory_database()


class BaseModel(Model):
    class Meta:
        database = db


class TestModel(BaseModel):
    name = CharField()
    number = IntegerField()


class Category(BaseModel):
    name = CharField()
    parent = ForeignKeyField('self', null=True, related_name='children')


class User(BaseModel):
    username = CharField()

    @hybrid_method
    def name_hash(self):
        return sum(map(ord, self.username)) % 10

    @hybrid_property
    def title(self):
        return self.username.title()

    @title.expression
    def title(self):
        return Expression(
            fn.UPPER(fn.SUBSTR(self.username, 1, 1)),
            OP_CONCAT,
            fn.SUBSTR(self.username, 2))


class Note(BaseModel):
    user = ForeignKeyField(User, related_name='notes')
    text = TextField()


class Tag(BaseModel):
    tag = CharField()


class NoteTag(BaseModel):
    note = ForeignKeyField(Note)
    tag = ForeignKeyField(Tag)


MODELS = [
    Category,
    User,
    Note,
    Tag,
    NoteTag]


class TestCastShortcut(ModelTestCase):
    requires = [User]

    def test_cast_shortcut(self):
        for username in ['100', '001', '101']:
            User.create(username=username)

        query = (User
                 .select(
                     User.username,
                     cast(User.username, 'int').alias('username_i'))
                 .order_by(SQL('username_i')))
        results = [(user.username, user.username_i) for user in query]
        self.assertEqual(results, [
            ('001', 1),
            ('100', 100),
            ('101', 101),
        ])


class TestCaseShortcut(ModelTestCase):
    requires = [TestModel]
    values = (
        ('alpha', 1),
        ('beta', 2),
        ('gamma', 3))

    expected = [
        {'name': 'alpha', 'number_string': 'one'},
        {'name': 'beta', 'number_string': 'two'},
        {'name': 'gamma', 'number_string': '?'},
    ]

    def setUp(self):
        super(TestCaseShortcut, self).setUp()

        for name, number in self.values:
            TestModel.create(name=name, number=number)

    def test_predicate(self):
        query = (TestModel
                 .select(TestModel.name, case(TestModel.number, (
                     (1, "one"),
                     (2, "two")), "?").alias('number_string'))
                 .order_by(TestModel.id))
        self.assertEqual(list(query.dicts()), self.expected)

    def test_no_predicate(self):
        query = (TestModel
                 .select(TestModel.name, case(None, (
                     (TestModel.number == 1, "one"),
                     (TestModel.number == 2, "two")), "?").alias('number_string'))
                 .order_by(TestModel.id))
        self.assertEqual(list(query.dicts()), self.expected)


class TestModelToDict(ModelTestCase):
    requires = MODELS

    def setUp(self):
        super(TestModelToDict, self).setUp()
        self.user = User.create(username='peewee')

    def test_simple(self):
        with assert_query_count(0):
            self.assertEqual(model_to_dict(self.user), {
                'id': self.user.id,
                'username': self.user.username})

    def test_simple_recurse(self):
        note = Note.create(user=self.user, text='note-1')

        with assert_query_count(0):
            self.assertEqual(model_to_dict(note), {
                'id': note.id,
                'text': note.text,
                'user': {
                    'id': self.user.id,
                    'username': self.user.username}})

        with assert_query_count(0):
            self.assertEqual(model_to_dict(note, recurse=False), {
                'id': note.id,
                'text': note.text,
                'user': self.user.id,
            })

    def test_simple_backref(self):
        with assert_query_count(1):
            self.assertEqual(model_to_dict(self.user, backrefs=True), {
                'id': self.user.id,
                'notes': [],
                'username': self.user.username})

        # Create a note to populate backrefs list.
        note = Note.create(user=self.user, text='note-1')

        expected = {
            'id': self.user.id,
            'notes': [
                {'id': note.id, 'notetag_set': [], 'text': note.text},
            ],
            'username': self.user.username}

        # Two queries: one to get related notes, one to get related notetags.
        with assert_query_count(2):
            self.assertEqual(
                model_to_dict(self.user, backrefs=True),
                expected)

        query = (User
                 .select(User, Note, NoteTag)
                 .join(Note, JOIN.LEFT_OUTER)
                 .join(NoteTag, JOIN.LEFT_OUTER)
                 .aggregate_rows())
        user = query.get()

        with assert_query_count(0):
            self.assertEqual(model_to_dict(user, backrefs=True), expected)

    def test_recurse_backrefs(self):
        note = Note.create(user=self.user, text='note-1')

        # One query to retrieve the note-tag set.
        with assert_query_count(1):
            self.assertEqual(model_to_dict(note, backrefs=True), {
                'id': note.id,
                'notetag_set': [],
                'text': note.text,
                'user': {
                    'id': self.user.id,
                    'username': self.user.username,
                },
            })

    def test_recursive_fk(self):
        root = Category.create(name='root')
        child = Category.create(name='child', parent=root)
        grandchild = Category.create(name='grandchild', parent=child)

        with assert_query_count(0):
            self.assertEqual(model_to_dict(root), {
                'id': root.id,
                'name': root.name,
                'parent': {},
            })

        with assert_query_count(0):
            self.assertEqual(model_to_dict(root, recurse=False), {
                'id': root.id,
                'name': root.name,
                'parent': None,
            })

        with assert_query_count(1):
            self.assertEqual(model_to_dict(root, backrefs=True), {
                'children': [{'id': child.id, 'name': child.name}],
                'id': root.id,
                'name': root.name,
                'parent': {},
            })

        with assert_query_count(1):
            self.assertEqual(model_to_dict(child, backrefs=True), {
                'children': [{'id': grandchild.id, 'name': grandchild.name}],
                'id': child.id,
                'name': child.name,
                'parent': {
                    'id': root.id,
                    'name': root.name,
                },
            })

        with assert_query_count(0):
            self.assertEqual(model_to_dict(child, backrefs=False), {
                'id': child.id,
                'name': child.name,
                'parent': {
                    'id': root.id,
                    'name': root.name,
                },
            })

    def test_many_to_many(self):
        note = Note.create(user=self.user, text='note-1')
        t1 = Tag.create(tag='t1')
        t2 = Tag.create(tag='t2')
        Tag.create(tag='tx')  # Note used on any notes.
        nt1 = NoteTag.create(note=note, tag=t1)
        nt2 = NoteTag.create(note=note, tag=t2)

        expected = {
            'id': self.user.id,
            'notes': [{
                'id': note.id,
                'notetag_set': [
                    {'id': nt1.id, 'tag': {'id': t1.id, 'tag': t1.tag}},
                    {'id': nt2.id, 'tag': {'id': t2.id, 'tag': t2.tag}},
                ],
                'text': note.text,
            }],
            'username': self.user.username,
        }

        # Query to retrieve notes, note-tags, and 2 tag queries.
        with assert_query_count(4):
            self.assertEqual(
                model_to_dict(self.user, backrefs=True),
                expected)

    def test_only(self):
        expected = {'username': self.user.username}
        self.assertEqual(
            model_to_dict(self.user, only=[User.username]),
            expected)

        self.assertEqual(
            model_to_dict(self.user, backrefs=True, only=[User.username]),
            expected)

        note = Note.create(user=self.user, text='note-1')
        expected = {'text': note.text, 'user': {
            'username': self.user.username}}
        self.assertEqual(
            model_to_dict(note, only=[Note.text, Note.user, User.username]),
            expected)
        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                only=[Note.text, Note.user, User.username]),
            expected)

        expected['user'] = self.user.id
        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                recurse=False,
                only=[Note.text, Note.user, User.username]),
            expected)

    def test_exclude(self):
        self.assertEqual(
            model_to_dict(self.user, exclude=[User.id]),
            {'username': self.user.username})

        self.assertEqual(
            model_to_dict(
                self.user,
                backrefs=True,
                exclude=[User.id, Note.user]),
            {'username': self.user.username})

        self.assertEqual(
            model_to_dict(
                self.user,
                backrefs=True,
                exclude=[User.id, User.notes]),
            {'username': self.user.username})

        note = Note.create(user=self.user, text='note-1')
        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                exclude=[Note.user, Note.notetag_set, Note.id]),
            {'text': note.text})

        self.assertEqual(
            model_to_dict(
                note,
                backrefs=True,
                exclude=[User.id, Note.notetag_set, Note.id]),
            {'text': note.text, 'user': {'username': self.user.username}})

    def test_extra_attrs(self):
        with assert_query_count(0):
            extra = ['name_hash', 'title']
            self.assertEqual(model_to_dict(self.user, extra_attrs=extra), {
                'id': self.user.id,
                'username': self.user.username,
                'name_hash': 5,
                'title': 'Peewee',
            })

        with assert_query_count(0):
            # Unknown attr causes AttributeError.
            def fails():
                model_to_dict(self.user, extra_attrs=['xx'])
            self.assertRaises(AttributeError, fails)


class TestDictToModel(ModelTestCase):
    requires = MODELS

    def setUp(self):
        super(TestDictToModel, self).setUp()
        self.user = User.create(username='charlie')

    def test_simple(self):
        data = {'username': 'charlie', 'id': self.user.id}
        inst = dict_to_model(User, data)
        self.assertTrue(isinstance(inst, User))
        self.assertEqual(inst.username, 'charlie')
        self.assertEqual(inst.id, self.user.id)

    def test_related(self):
        data = {
            'id': 2,
            'text': 'note-1',
            'user': {
                'id': self.user.id,
                'username': 'charlie'}}

        with assert_query_count(0):
            inst = dict_to_model(Note, data)
            self.assertTrue(isinstance(inst, Note))
            self.assertEqual(inst.id, 2)
            self.assertEqual(inst.text, 'note-1')
            self.assertTrue(isinstance(inst.user, User))
            self.assertEqual(inst.user.id, self.user.id)
            self.assertEqual(inst.user.username, 'charlie')

        data['user'] = self.user.id

        with assert_query_count(0):
            inst = dict_to_model(Note, data)

        with assert_query_count(1):
            self.assertEqual(inst.user, self.user)

    def test_backrefs(self):
        data = {
            'id': self.user.id,
            'username': 'charlie',
            'notes': [
                {'id': 1, 'text': 'note-1'},
                {'id': 2, 'text': 'note-2'},
            ]}

        with assert_query_count(0):
            inst = dict_to_model(User, data)
            self.assertEqual(inst.id, self.user.id)
            self.assertEqual(inst.username, 'charlie')
            self.assertTrue(isinstance(inst.notes, list))

            note_1, note_2 = inst.notes
            self.assertEqual(note_1.id, 1)
            self.assertEqual(note_1.text, 'note-1')
            self.assertEqual(note_1.user, self.user)

            self.assertEqual(note_2.id, 2)
            self.assertEqual(note_2.text, 'note-2')
            self.assertEqual(note_2.user, self.user)

    def test_unknown_attributes(self):
        data = {
            'id': self.user.id,
            'username': 'peewee',
            'xx': 'does not exist'}
        self.assertRaises(
            AttributeError,
            dict_to_model,
            User,
            data)

        inst = dict_to_model(User, data, ignore_unknown=True)
        self.assertEqual(inst.xx, 'does not exist')
