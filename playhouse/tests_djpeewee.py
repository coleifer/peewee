import unittest

from peewee import *
from peewee import print_
try:
    import django
except ImportError:
    django = None


if django is not None:
    from django.conf import settings
    settings.configure(
        DATABASES={
            'default': {
                'engine': 'django.db.backends.sqlite3',
                'name': ':memory:'}},
    )
    from django.db import models
    from playhouse.djpeewee import translate

    # Django model definitions.
    class Simple(models.Model):
        char_field = models.CharField(max_length=1)
        int_field = models.IntegerField()

    class User(models.Model):
        username = models.CharField(max_length=255)

        class Meta:
            db_table = 'user_tbl'

    class Post(models.Model):
        author = models.ForeignKey(User, related_name='posts')
        content = models.TextField()

    class Comment(models.Model):
        post = models.ForeignKey(Post, related_name='comments')
        commenter = models.ForeignKey(User, related_name='comments')
        comment = models.TextField()

    class Tag(models.Model):
        tag = models.CharField()
        posts = models.ManyToManyField(Post)

    class TestDjPeewee(unittest.TestCase):
        def assertFields(self, model, expected):
            zipped = zip(model._meta.get_fields(), expected)
            for (model_field, (name, field_type)) in zipped:
                self.assertEqual(model_field.name, name)
                self.assertEqual(type(model_field), field_type)

        def test_simple(self):
            P = translate(Simple)
            self.assertEqual(P.keys(), ['Simple'])
            self.assertFields(P['Simple'], [
                ('id', PrimaryKeyField),
                ('char_field', CharField),
                ('int_field', IntegerField),
            ])

        def test_graph(self):
            P = translate(User, Tag, Comment)
            self.assertEqual(sorted(P.keys()), [
                'Comment',
                'Post',
                'Tag',
                'Tag_posts',
                'User'])

            # Test the models that were found.
            user = P['User']
            self.assertFields(user, [
                ('id', PrimaryKeyField),
                ('username', CharField)])
            self.assertEqual(user.posts.rel_model, P['Post'])
            self.assertEqual(user.comments.rel_model, P['Comment'])

            post = P['Post']
            self.assertFields(post, [
                ('id', PrimaryKeyField),
                ('author', ForeignKeyField),
                ('content', TextField)])
            self.assertEqual(post.comments.rel_model, P['Comment'])

            comment = P['Comment']
            self.assertFields(comment, [
                ('id', PrimaryKeyField),
                ('post', ForeignKeyField),
                ('commenter', ForeignKeyField),
                ('comment', TextField)])

            tag = P['Tag']
            self.assertFields(tag, [
                ('id', PrimaryKeyField),
                ('tag', CharField)])

            thru = P['Tag_posts']
            self.assertFields(thru, [
                ('id', PrimaryKeyField),
                ('tag', ForeignKeyField),
                ('post', ForeignKeyField)])

        def test_fk_query(self):
            trans = translate(User, Post, Comment, Tag)
            U = trans['User']
            P = trans['Post']
            C = trans['Comment']

            query = (U.select()
                     .join(P)
                     .join(C)
                     .where(C.comment == 'test'))
            sql, params = query.sql()
            self.assertEqual(
                sql,
                'SELECT t1."id", t1."username" FROM "user_tbl" AS t1 '
                'INNER JOIN "playhouse_post" AS t2 '
                'ON (t1."id" = t2."author_id") '
                'INNER JOIN "playhouse_comment" AS t3 '
                'ON (t2."id" = t3."post_id") WHERE (t3."comment" = ?)')
            self.assertEqual(params, ['test'])

        def test_m2m_query(self):
            trans = translate(Post, Tag)
            P = trans['Post']
            U = trans['User']
            T = trans['Tag']
            TP = trans['Tag_posts']

            query = (P.select(P, U)
                     .join(U)
                     .switch(P)
                     .join(TP)
                     .join(T)
                     .where(T.tag == 'test'))
            sql, params = query.sql()
            self.assertEqual(
                sql,
                'SELECT t1."id", t1."author_id", t1."content", '
                't4."id", t4."username" FROM "playhouse_post" AS t1 '
                'INNER JOIN "user_tbl" AS t4 '
                'ON (t1."author_id" = t4."id") '
                'INNER JOIN "playhouse_tag_posts" AS t2 '
                'ON (t1."id" = t2."post_id") '
                'INNER JOIN "playhouse_tag" AS t3 '
                'ON (t2."tag_id" = t3."id") WHERE (t3."tag" = ?)')
            self.assertEqual(params, ['test'])


else:
    print_('Skipping djpeewee tests, Django not found.')
