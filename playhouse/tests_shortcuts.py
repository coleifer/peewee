import unittest

from peewee import *
from playhouse.shortcuts import *
from playhouse.test_utils import assert_query_count


db = SqliteDatabase(':memory:')

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

class CaseShortcutTestCase(unittest.TestCase):
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
        TestModel.drop_table(True)
        TestModel.create_table()

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


class TestModelToDict(unittest.TestCase):
    def setUp(self):
        db.drop_tables(MODELS, safe=True)
        db.create_tables(MODELS)

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
                 .join(Note, JOIN_LEFT_OUTER)
                 .join(NoteTag, JOIN_LEFT_OUTER)
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


class TestDictToModel(unittest.TestCase):
    def setUp(self):
        db.drop_tables(MODELS, safe=True)
        db.create_tables(MODELS)
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
