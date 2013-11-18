"""
Simple translation of Django model classes to peewee model classes.
"""
from functools import partial
import logging

from peewee import *

logger = logging.getLogger('peewee.playhouse.djpeewee')

class AttrDict(dict):
    def __getattr__(self, attr):
        return self[attr]

class DjangoTranslator(object):
    def __init__(self):
        self._field_map = self.get_django_field_map()

    def get_django_field_map(self):
        from django.db.models import fields as djf
        return [
            (djf.AutoField, PrimaryKeyField),
            (djf.BigIntegerField, BigIntegerField),
            #(djf.BinaryField, BlobField),
            (djf.BooleanField, BooleanField),
            (djf.CharField, CharField),
            (djf.DateTimeField, DateTimeField),  # Extends DateField.
            (djf.DateField, DateField),
            (djf.DecimalField, DecimalField),
            (djf.FilePathField, CharField),
            (djf.FloatField, FloatField),
            (djf.IntegerField, IntegerField),
            (djf.NullBooleanField, partial(BooleanField, null=True)),
            (djf.TextField, TextField),
            (djf.TimeField, TimeField),
            (djf.related.ForeignKey, ForeignKeyField),
        ]

    def _translate_model(self, model, mapping):
        from django.db.models import fields as djf
        options = model._meta
        if mapping.get(options.object_name):
            return

        attrs = {}
        # Sort fields such that nullable fields appear last.
        field_key = lambda field: (field.null and 1 or 0, field)
        for model_field in sorted(options.fields, key=field_key):
            # Find the appropriate peewee field class.
            converted = None
            for django_field, peewee_field in self._field_map:
                if isinstance(model_field, django_field):
                    converted = peewee_field
                    break

            # Special-case ForeignKey fields.
            if converted is ForeignKeyField:
                related_model = model_field.rel.to
                model_name = related_model._meta.object_name
                # If we haven't processed the related model yet, do so now.
                if model_name not in mapping:
                    mapping[model_name] = None  # Avoid endless recursion.
                    self._translate_model(related_model, mapping)
                if mapping[model_name] is None:
                    # Put an integer field here.
                    logger.warn('Cycle detected: %s: %s',
                                model_field.name, model_name)
                    mapping[model_name] = IntegerField(
                        db_column=model_field.get_attname())
                else:
                    related_name = model_field.related_query_name()
                    if related_name.endswith('+'):
                        related_name = '__%s:%s:%s' % (
                            options,
                            model_field.name,
                            related_name.strip('+'))

                    attrs[model_field.name] = ForeignKeyField(
                        mapping[model_name],
                        related_name=related_name)

            elif converted:
                attrs[model_field.name] = converted()

        klass = type(options.object_name, (Model,), attrs)
        klass._meta.db_table = options.db_table
        klass._meta.database.interpolation = '%s'
        mapping[options.object_name] = klass

        # Load up many-to-many relationships.
        for many_to_many in options.many_to_many:
            if not isinstance(many_to_many, djf.related.ManyToManyField):
                continue
            self._translate_model(many_to_many.rel.through, mapping)


    def translate_models(self, *models):
        """
        Generate a group of peewee models analagous to the provided Django models
        for the purposes of creating queries.

        :param model: A Django model class.
        :returns: A dictionary mapping model names to peewee model classes.
        :rtype: dict

        Example::

            # Map Django models to peewee models. Foreign keys and M2M will be
            # traversed as well.
            peewee = translate(Account)

            # Generate query using peewee.
            PUser = peewee['User']
            PAccount = peewee['Account']
            query = PUser.select().join(PAccount).where(PAccount.acct_type == 'foo')

            # Django raw query.
            users = User.objects.raw(*query.sql())
        """
        mapping = AttrDict()
        for model in models:
            self._translate_model(model, mapping)
        return mapping

try:
    import django
    translate = DjangoTranslator().translate_models
except ImportError:
    pass
