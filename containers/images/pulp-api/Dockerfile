FROM centos:7

ARG PLUGINS=""

# mariadb_devel needed to avoid error installing pulpcore[mysql] (post-rc1)
# otherwise, `mysql_config` is not found
# It also needs gcc at least, so we install the dev tools package group.
# And it needs Python.h
RUN echo "tsflags=nodocs" >> /etc/yum.conf && \
		yum -y update && \
		yum -y install epel-release centos-release-scl && \
		yum -y install wget git rh-python36-python-pip && \
		yum -y install @development mariadb-devel rh-python36-python-devel && \
		yum clean all

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONUNBUFFERED=0
ENV DJANGO_SETTINGS_MODULE=pulpcore.app.settings

RUN mkdir -p /etc/pulp

RUN scl enable rh-python36 'pip install gunicorn'
RUN scl enable rh-python36 'pip install git+https://github.com/pulp/pulpcore.git'
RUN scl enable rh-python36 'pip install git+https://github.com/pulp/pulpcore-plugin.git'
RUN scl enable rh-python36 'pip install git+https://github.com/pulp/pulpcore.git#egg=pulpcore[postgres]'
RUN scl enable rh-python36 'pip install git+https://github.com/pulp/pulpcore.git#egg=pulpcore[mysql]'
RUN scl enable rh-python36 'pip install $PLUGINS'

RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulpcore/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulpcore/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulp_file/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulp_ansible/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulp_cookbook/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulp_docker/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulp_maven/app/migrations
RUN mkdir -p /opt/rh/rh-python36/root/usr/lib/python3.6/site-packages/pulp_python/app/migrations

COPY container-assets/wait_on_postgres.py /usr/bin/wait_on_postgres.py
COPY container-assets/wait_on_database_migrations.sh /usr/bin/wait_on_database_migrations.sh
COPY container-assets/pulp-common-entrypoint.sh /pulp-common-entrypoint.sh
COPY container-assets/pulp-api /usr/bin/pulp-api

ENTRYPOINT ["/pulp-common-entrypoint.sh"]
CMD ["/usr/bin/pulp-api"]
