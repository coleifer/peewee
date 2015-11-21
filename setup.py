import os
from distutils.core import setup
from distutils.extension import Extension

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()

setup_kwargs = {}
try:
    from Cython.Distutils import build_ext
except ImportError:
    pass
else:
    speedups_ext_module = Extension(
        'playhouse._speedups',
        ['playhouse/speedups.pyx'])
    sqlite_ext_module = Extension(
        'playhouse._sqlite_ext',
        ['playhouse/_sqlite_ext.pyx'])

    class BuildSqliteExt(build_ext):
        def run(self):
            self._original_modules = self.distribution.ext_modules
            try:
                self.extensions = [sqlite_ext_module]
                return build_ext.run(self)
            finally:
                self.distribution.ext_modules = self._original_modules

    setup_kwargs.update(
        cmdclass={
            'build_ext': build_ext,
            'build_sqlite_ext': BuildSqliteExt},
        ext_modules=[speedups_ext_module])


setup(
    name='peewee',
    version=__import__('peewee').__version__,
    description='a little orm',
    long_description=readme,
    author='Charles Leifer',
    author_email='coleifer@gmail.com',
    url='http://github.com/coleifer/peewee/',
    packages=['playhouse'],
    py_modules=['peewee', 'pwiz'],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    test_suite='tests',
    scripts = ['pwiz.py'],
    **setup_kwargs
)
