"""
Provide django-style hooks for model events.
"""
from peewee import Model as _Model
from peewee import logger


class Signal(object):
    def __init__(self):
        self._flush()

    def connect(self, receiver, name=None, sender=None):
        name = name or receiver.__name__
        if (receiver, sender) == self._receivers.get(name):
            logger.warning('receiver %s has been already connected' % name)
            return

        if name not in self._receivers:
            self._receivers[name] = (receiver, sender)
            self._receiver_list.append(name)
        else:
            _, connected_sender = self._receivers[name]
            if str(sender) != str(connected_sender):
                raise ValueError(
                    'receiver %s is already attached to another sender %s' %
                    (name, connected_sender)
                )
            else:
                # Update code for receiver
                self._receivers[name] = (receiver, sender)

    def disconnect(self, receiver=None, name=None):
        if receiver:
            name = receiver.__name__
        if name:
            del self._receivers[name]
            self._receiver_list.remove(name)
        else:
            raise ValueError('a receiver or a name must be provided')

    def __call__(self, name=None, sender=None):
        def decorator(fn):
            self.connect(fn, name, sender)
            return fn
        return decorator

    def send(self, instance, *args, **kwargs):
        sender = type(instance)
        responses = []
        for name in self._receiver_list:
            r, s = self._receivers[name]
            if s is None or isinstance(instance, s):
                responses.append((r, r(sender, instance, *args, **kwargs)))
        return responses

    def _flush(self):
        self._receivers = {}
        self._receiver_list = []


pre_save = Signal()
post_save = Signal()
pre_delete = Signal()
post_delete = Signal()
pre_init = Signal()


class Model(_Model):
    def __init__(self, *args, **kwargs):
        super(Model, self).__init__(*args, **kwargs)
        pre_init.send(self)

    def save(self, *args, **kwargs):
        pk_value = self._pk
        created = kwargs.get('force_insert', False) or not bool(pk_value)
        pre_save.send(self, created=created)
        ret = super(Model, self).save(*args, **kwargs)
        post_save.send(self, created=created)
        return ret

    def delete_instance(self, *args, **kwargs):
        pre_delete.send(self)
        ret = super(Model, self).delete_instance(*args, **kwargs)
        post_delete.send(self)
        return ret
