from setuptools import find_packages, setup

with open("README.md") as f:
    long_description = f.read()

with open("requirements.txt") as requirements:
    requirements = requirements.readlines()

with open("functest_requirements.txt") as test_requirements:
    test_requirements = test_requirements.readlines()

setup(
    name="pulpcore",
    version="3.9.1",
    description="Pulp Django Application and Related Modules",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="GPLv2+",
    packages=find_packages(exclude=["test"]),
    author="Pulp Team",
    author_email="pulp-list@redhat.com",
    url="https://pulpproject.org",
    python_requires=">=3.6",
    install_requires=requirements,
    extras_require={
        "s3": ["django-storages[boto3]"],
        "azure": ["django-storages[azure]"],
        "prometheus": ["django-prometheus"],
        "test": test_requirements,
    },
    include_package_data=True,
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
        "Operating System :: POSIX :: Linux",
        "Development Status :: 5 - Production/Stable",
        "Framework :: Django",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    scripts=["bin/pulp-content"],
    entry_points={"console_scripts": ["pulpcore-manager = pulpcore.app.manage:manage"]},
)
