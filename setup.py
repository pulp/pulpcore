from setuptools import find_packages, setup

with open('README.md') as f:
    long_description = f.read()

requirements = [
    'coreapi',
    'Django~=2.2',  # LTS version, switch only if we have a compelling reason to
    'django-filter',
    'djangorestframework<3.10',
    'djangorestframework-queryfields',
    'drf-nested-routers',
    'drf-yasg',
    'gunicorn',
    'packaging',  # until drf-yasg 1.16.2 is out https://github.com/axnsan12/drf-yasg/issues/412
    'PyYAML',
    'rq~=1.0',
    'redis<3.2.0',
    'setuptools',
    'dynaconf~=2.0',
    'whitenoise',
]

setup(
    name='pulpcore',
    version='3.0.0rc4',
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
