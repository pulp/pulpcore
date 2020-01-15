from setuptools import find_packages, setup

with open('README.md') as f:
    long_description = f.read()

requirements = [
    'aiohttp',
    'aiofiles',
    'backoff',
    'coreapi~=2.3.3',
    'Django~=2.2.3',  # LTS version, switch only if we have a compelling reason to
    'django-filter~=2.2.0',
    'djangorestframework~=3.10.2',
    'djangorestframework-queryfields~=1.0.0',
    'drf-nested-routers~=0.91.0',
    'drf-yasg~=1.17.0',
    'gunicorn>=19.9,<20.1',
    'psycopg2>=2.7,<2.9',
    'PyYAML>=5.1.1,<5.3.0',
    'rq~=1.1.0',
    'redis~=3.1.0',
    'setuptools>=39.2.0,<42.1.0',
    'dynaconf>=2.2,<2.3',
    'whitenoise~=4.1.3',
    'pygtrie~=2.3.2',
]

setup(
    name='pulpcore',
    version='3.0.1',
    description='Pulp Django Application and Related Modules',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='GPLv2+',
    packages=find_packages(exclude=['test']),
    author='Pulp Team',
    author_email='pulp-list@redhat.com',
    url='https://pulpproject.org',
    python_requires='>=3.6',
    install_requires=requirements,
    include_package_data=True,
    classifiers=(
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: POSIX :: Linux',
        'Development Status :: 5 - Production/Stable',
        'Framework :: Django',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ),
    scripts=['bin/pulp-content'],
)
