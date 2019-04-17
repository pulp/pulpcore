FROM centos:7

ARG PLUGINS=""

RUN echo "tsflags=nodocs" >> /etc/yum.conf && \
		yum -y install epel-release centos-release-scl && \
		yum -y install wget git rh-python36-python-pip && \
		yum clean all

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PYTHONUNBUFFERED=0
ENV DJANGO_SETTINGS_MODULE=pulpcore.app.settings

RUN mkdir -p /etc/pulp

RUN scl enable rh-python36 'pip install gunicorn'
RUN scl enable rh-python36 'pip install pulpcore'
RUN scl enable rh-python36 'pip install pulpcore-plugin pulpcore[postgres] pulpcore[mysql]'
RUN scl enable rh-python36 'pip install $PLUGINS'

RUN scl enable rh-python36 "django-admin collectstatic --noinput"

COPY container-assets/wait_on_postgres.py /usr/bin/wait_on_postgres.py
COPY container-assets/wait_on_database_migrations.sh /usr/bin/wait_on_database_migrations.sh
COPY container-assets/pulp-api /usr/bin/pulp-api


CMD ["/usr/bin/pulp-api"]
