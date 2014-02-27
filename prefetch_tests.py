import logging
import sys

import tests


logger = logging.getLogger('peewee')
logger.setLevel(logging.DEBUG)
hndlr = logging.StreamHandler(sys.stdout)

class PrefetchRelatedTestCase(tests.PrefetchTestCase):
    prefetch_string = 'blog_set__comments'
    def test_prefetch_simple(self):
        sq = self.user_model.select().where(self.user_model.username != 'u3')
        qc = len(self.queries())

        prefetch_sq = sq.prefetch_related('blog_set__comments')
        results = []
        for user in prefetch_sq:
            results.append(user.username)
            for blog in user.blog_set:
                results.append(blog.title)
                for comment in blog.comments:
                    results.append(comment.comment)

        self.assertEqual(results, [
            'u1', 'b1', 'b1-c1', 'b1-c2', 'b2', 'b2-c1',
            'u2',
            'u4', 'b5', 'b5-c1', 'b5-c2', 'b6', 'b6-c1',
        ])
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 3)

        results = []
        for user in prefetch_sq:
            for blog in user.blog_set:
                results.append(blog.user.username)
                for comment in blog.comments:
                    results.append(comment.blog.title)
        self.assertEqual(results, [
            'u1', 'b1', 'b1', 'u1', 'b2', 'u4', 'b5', 'b5', 'u4', 'b6',
        ])
        qc3 = len(self.queries())
        self.assertEqual(qc3, qc2)

    def test_nonprefetch_simple(self):
        sq = self.user_model.select().where(self.user_model.username != 'u3')
        qc = len(self.queries())

        prefetch_sq = sq
        results = []
        for user in prefetch_sq:
            results.append(user.username)
            for blog in user.blog_set:
                results.append(blog.title)
                for comment in blog.comments:
                    results.append(comment.comment)

        self.assertEqual(results, [
            'u1', 'b1', 'b1-c1', 'b1-c2', 'b2', 'b2-c1',
            'u2',
            'u4', 'b5', 'b5-c1', 'b5-c2', 'b6', 'b6-c1',
        ])
        qc2 = len(self.queries())
        self.assertEqual(qc2 - qc, 1 + 3 + 4)

        results = []
        for user in prefetch_sq:
            results.append(user.username)
            for blog in user.blog_set:
                results.append(blog.title)
                for comment in blog.comments:
                    results.append(comment.comment)
        self.assertEqual(results, [
            'u1', 'b1', 'b1-c1', 'b1-c2', 'b2', 'b2-c1',
            'u2',
            'u4', 'b5', 'b5-c1', 'b5-c2', 'b6', 'b6-c1',
        ])
        qc3 = len(self.queries())
        self.assertEqual(qc3, qc2)

        results = []
        for user in prefetch_sq:
            for blog in user.blog_set:
                results.append(blog.user.username)
                for comment in blog.comments:
                    results.append(comment.blog.title)
        self.assertEqual(results, [
            'u1', 'b1', 'b1', 'u1', 'b2', 'u4', 'b5', 'b5', 'u4', 'b6',
        ])
        qc4 = len(self.queries())
        self.assertEqual(qc4, qc3)

class PrefetchRelatedWithToFieldTestCase(PrefetchRelatedTestCase):
    requires = [tests.UserToField, tests.BlogToField, tests.CommentToField, tests.Parent, tests.Child, tests.Orphan, tests.ChildPet, tests.OrphanPet, tests.Category]
    blog_model = tests.BlogToField
    user_model = tests.UserToField
    comment_model = tests.CommentToField
