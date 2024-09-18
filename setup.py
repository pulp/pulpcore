from setuptools import find_packages, setup

with open("README.md") as f:
    long_description = f.read()

with open("requirements.txt") as requirements:
    requirements = requirements.readlines()

setup(
    name="pulpcore",
    version="3.49.20",
    description="Pulp Django Application and Related Modules",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="GPLv2+",
    packages=find_packages(),
    author="Pulp Team",
    author_email="pulp-list@redhat.com",
    url="https://pulpproject.org",
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "sftp": ["django-storages[sftp]<=1.13.2"],
        "s3": ["django-storages[boto3]<=1.13.2"],
        "google": ["django-storages[google]>=1.13.2,<=1.13.2"],
        "azure": ["django-storages[azure]>=1.12.2,<=1.13.2"],
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
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    entry_points={
        "console_scripts": [
            "pulpcore-manager = pulpcore.app.manage:manage",
            "pulpcore-worker = pulpcore.tasking.entrypoint:worker",
            "pulpcore-api = pulpcore.app.entrypoint:main",
            "pulpcore-content = pulpcore.content.entrypoint:main",
        ],
        "pulpcore.plugin": [
            "pulp_file = pulp_file:default_app_config",
            "pulp_certguard = pulp_certguard:default_app_config",
        ],
        "pytest11": [
            "pulpcore = pulpcore.tests.functional",
            "pulp_file = pulp_file.pytest_plugin",
            "pulp_certguard = pulp_certguard.pytest_plugin",
        ],
    },
)
