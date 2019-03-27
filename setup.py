from setuptools import setup, find_packages

with open('README.md') as f:
    long_description = f.read()

requirements = [
    'coreapi',
    'Django>=2.0',
    'django-filter',
    'djangorestframework',
    'djangorestframework-queryfields',
    'drf-nested-routers',
    'drf-yasg',
    'gunicorn',
    'PyYAML',
    'rq>=0.12,<1.0',
    'redis<3.2.0',
    'setuptools',
    'dynaconf>=1.0.4',
    'whitenoise',
    'drf-chunked-upload'
]

setup(
    name='pulpcore',
    version='3.0.0rc1',
    description='Pulp Django Application and Related Modules',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='GPLv2+',
    packages=find_packages(exclude=['test']),
    author='Pulp Team',
    author_email='pulp-list@redhat.com',
    url='http://www.pulpproject.org',
    python_requires='>=3.6',
    install_requires=requirements,
    extras_require={
        'postgres': ['psycopg2-binary'],
        'mysql': ['mysqlclient']
    },
    include_package_data=True,
    classifiers=(
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: POSIX :: Linux',
        'Development Status :: 4 - Beta',
        'Framework :: Django',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ),
    scripts=['bin/pulp-content'],
)
