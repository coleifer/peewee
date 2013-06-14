import datetime
import os

from models import Blog
from models import Entry
from models import User


def initialize():
    from django.core.management import call_command
    call_command('syncdb')

def teardown():
    from django.db import connection
    curs = connection.cursor()
    curs.execute('DROP TABLE django_bench_entry;')
    curs.execute('DROP TABLE django_bench_blog;')
    curs.execute('DROP TABLE django_bench_user;')

def create_user(username, active=True):
    return User.objects.create(username=username, active=active)

def create_blog(user, name):
    return Blog.objects.create(user=user, name=name)

def create_entry(blog, title, content, pub_date=None):
    return Entry.objects.create(blog=blog, title=title, content=content,
                                pub_date=pub_date or datetime.datetime.now())

def list_users(ordered=False):
    if ordered:
        qs = User.objects.all().order_by('username')
    else:
        qs = User.objects.all()
    return list(qs)

def list_blogs_select_related():
    qs = Blog.objects.all().select_related('user')
    return list(qs)

def list_blogs_for_user(user):
    return list(user.blog_set.all())

def list_entries_by_user(user):
    return list(Entry.objects.filter(blog__user=user))

def get_user_count():
    return User.objects.all().count()

def list_entries_subquery(user):
    return list(Entry.objects.filter(blog__in=Blog.objects.filter(user=user)))

def get_user(username):
    return User.objects.get(username=username)

def get_or_create_user(username):
    return User.objects.get_or_create(username=username)
