from collections import Counter
import hashlib
import math


class Accumulator(object):
    def __init__(self):
        self.values = []

    def step(self, *values):
        self.values.extend(values)

class Variance(Accumulator):
    def finalize(self):
        mean = sum(self.values) / float(len(self.values))
        squares = [(val - mean) ** 2 for val in self.values]
        return sum(squares) / len(squares)

class StdDev(Variance):
    def finalize(self):
        return math.sqrt(super(StdDev, self).finalize())

class CSV(Accumulator):
    def finalize(self):
        return ','.join(map(str, self.values))

class Mode(object):
    def __init__(self):
        self.counter = Counter()

    def step(self, *values):
        self.counter.update(values)

    def finalize(self):
        most_common = self.counter.most_common(1)
        if most_common:
            return most_common[0][0]

class MD5Sum(object):
    def __init__(self):
        self.md5 = hashlib.md5()

    def step(self, value):
        self.md5.update(str(value))

    def finalize(self):
        return self.md5.hexdigest()

class SHA1Sum(object):
    def __init__(self):
        self.sha1 = hashlib.sha1()

    def step(self, value):
        self.sha1.update(str(value))

    def finalize(self):
        return self.sha1.hexdigest()

class First(object):
    def __init__(self):
        self.sentinel = object()
        self.value = self.sentinel

    def step(self, value):
        if self.value is self.sentinel:
            self.value = value

    def finalize(self):
        if self.value is not self.sentinel:
            return self.value

class Last(object):
    def __init__(self):
        self.value = None

    def step(self, value):
        self.value = value

    def finalize(self):
        return self.value
