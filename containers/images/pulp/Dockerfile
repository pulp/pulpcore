FROM fedora:30

ARG PULPCORE
ARG PULPCORE_PLUGIN
ARG PLUGINS

# https://superuser.com/questions/959380/how-do-i-install-generate-all-locales-on-fedora
# This may not be necessary anymore because Fedora 30, unlike CentOS 7, has
# glibc subpackages like glibc-langpack-en.
RUN rm /etc/rpm/macros.image-language-conf
RUN echo 'LANG="en_US.UTF-8"' > /etc/locale.conf
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONUNBUFFERED=0
ENV DJANGO_SETTINGS_MODULE=pulpcore.app.settings

# The Fedora 30 image already has tsflags=nodocs set in dnf.conf
# It already has pip
#
# wget & git are presumably needed for purposes like pip installs from git
#
# libxcrypt-compat is needed by psycopg2-binary from PyPI
#
# python3-psycopg2 is installed by ansible-pulp
#
# glibc-langpack-en is needed to provide the en_US.UTF-8 locale, which Pulp
# seems to need.
#
# The development packages are needed for installing nightly versions with pip.
# @c-development is the closest equivalent of EL7's "@development" group.
#
# Also installing the long list of pulp-rpm deps from
# https://github.com/pulp/pulp-rpm-prerequisites/blob/master/vars/Fedora.yml
# (Including it literally, dups @c-development won't slow down dnf much)
RUN		dnf -y update && \
		dnf -y install wget git && \
		dnf -y install libxcrypt-compat && \
		dnf -y install python3-psycopg2 && \
		dnf -y install glibc-langpack-en && \
		dnf -y install @c-development python3-devel && \
		dnf -y install gcc make cmake bzip2-devel expat-devel file-devel glib2-devel libcurl-devel libmodulemd-devel libxml2-devel python3-devel python3-libmodulemd rpm-devel openssl-devel sqlite-devel xz-devel zchunk-devel zlib-devel && \
		dnf clean all

# Docs suggest RHEL8 uses the alternatives system for /usr/bin/python ,
# but Fedora does not.
RUN ln -s /usr/bin/python3 /usr/bin/python
# If pip2 is installed, it will replace /usr/bin/pip .
# /usr/local/bin will be before it in the PATH .
RUN ln -s /usr/bin/pip3 /usr/local/bin/pip

RUN mkdir -p /etc/pulp

RUN pip install gunicorn
RUN pip install $PULPCORE
RUN pip install $PULPCORE_PLUGIN
RUN pip install ${PULPCORE}[postgres]
RUN test -z "$PLUGINS" || pip install $PLUGINS

RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulpcore/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_file/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_ansible/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_cookbook/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_docker/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_maven/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_python/app/migrations
RUN mkdir -p /usr/local/lib/python3.7/site-packages/pulp_rpm/app/migrations

COPY container-assets/wait_on_postgres.py /usr/bin/wait_on_postgres.py
COPY container-assets/wait_on_database_migrations.sh /usr/bin/wait_on_database_migrations.sh
COPY container-assets/pulp-common-entrypoint.sh /pulp-common-entrypoint.sh
COPY container-assets/pulp-api /usr/bin/pulp-api
COPY container-assets/pulp-content /usr/bin/pulp-content
COPY container-assets/pulp-resource-manager /usr/bin/pulp-resource-manager
COPY container-assets/pulp-worker /usr/bin/pulp-worker


ENTRYPOINT ["/pulp-common-entrypoint.sh"]
