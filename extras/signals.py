from peewee import Model as _Model


class Signal(object):
    def __init__(self):
        self._flush()

    def connect(self, receiver, name=None, sender=None):
        name = name or receiver.__name__
        if name not in self._receivers:
            self._receivers[name] = (receiver, sender)
            self._receiver_list.append(name)
        else:
            raise ValueError('receiver named %s already connected' % name)

    def disconnect(self, receiver=None, name=None):
        if receiver:
            name = receiver.__name__
        if name:
            del self._receivers[name]
            self._receiver_list.remove(name)
        else:
            raise ValueError('a receiver or a name must be provided')

    def send(self, instance, *args, **kwargs):
        sender = type(instance)
        responses = []
        for name in self._receiver_list:
            r, s = self._receivers[name]
            if s is None or sender is s:
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
post_init = Signal()


class Model(_Model):
    def __init__(self, *args, **kwargs):
        super(Model, self).__init__(*args, **kwargs)
        pre_init.send(self)

    def prepared(self):
        super(Model, self).prepared()
        post_init.send(self)

    def save(self, *args, **kwargs):
        created = not bool(self.get_pk())
        pre_save.send(self, created=created)
        super(Model, self).save(*args, **kwargs)
        post_save.send(self, created=created)

    def delete_instance(self, *args, **kwargs):
        pre_delete.send(self)
        super(Model, self).delete_instance(*args, **kwargs)
        post_delete.send(self)

def connect(signal, name=None, sender=None):
    def decorator(fn):
        signal.connect(fn, name, sender)
        return fn
    return decorator
