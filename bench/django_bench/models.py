from django.conf import settings

settings.configure(
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': 'test_dj.db',
        }
    },
    INSTALLED_APPS = ('django_bench',)
)

from django.db import models


class User(models.Model):
    username = models.CharField(max_length=255)
    active = models.BooleanField(default=True)


class Blog(models.Model):
    user = models.ForeignKey(User)
    name = models.CharField(max_length=255)


class Entry(models.Model):
    blog = models.ForeignKey(Blog)
    title = models.CharField(max_length=255)
    content = models.TextField()
    pub_date = models.DateTimeField()
