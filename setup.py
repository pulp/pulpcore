from setuptools import find_packages, setup

with open("README.md") as f:
    long_description = f.read()

with open("requirements.txt") as requirements:
    requirements = requirements.readlines()

setup(
    name="pulpcore",
    version="3.18.13",
    description="Pulp Django Application and Related Modules",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="GPLv2+",
    packages=find_packages(exclude=["test"]),
    author="Pulp Team",
    author_email="pulp-list@redhat.com",
    url="https://pulpproject.org",
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "s3": ["django-storages[boto3]"],
        "azure": ["django-storages[azure]>=1.12.2"],
        "prometheus": ["django-prometheus"],
    },
    include_package_data=True,
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
        "Operating System :: POSIX :: Linux",
        "Development Status :: 5 - Production/Stable",
        "Framework :: Django",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    scripts=["bin/pulp-content"],
    entry_points={
        "console_scripts": [
            "pulpcore-manager = pulpcore.app.manage:manage",
            "pulpcore-worker = pulpcore.tasking.entrypoint:worker",
        ],
        "pytest11": ["pulpcore = pulpcore.tests.functional"],
    },
)
