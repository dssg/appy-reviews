# appy-reviews container build file
#

ARG PYVERSION=3.7.12

FROM python:$PYVERSION-bullseye

# build for production by default, but allow use of alternative Python
# requirement files for alternative runtime targets (such as development)
ARG TARGET=production

# redeclare PYVERSION argument for access in label (FIXME: does this work?)
ARG PYVERSION

LABEL version="0.4" \
      pyversion="$PYVERSION" \
      target="$TARGET"

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
      # manage web processes:
      supervisor \
      # for command reporting:
      devscripts \
      time \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd webapp \
    && useradd webapp -g webapp
RUN mkdir -p /var/log/webapp \
    && chown webapp /var/log/webapp \
    && chmod ug+rx /var/log/webapp
RUN mkdir -p /var/run/webapp \
    && chown webapp /var/run/webapp \
    && chmod ug+rx /var/run/webapp

RUN mkdir -p /var/log/supervisor
COPY supervisor.conf /etc/supervisor/conf.d/webapp.conf

RUN mkdir -p /etc/webapp
COPY gunicorn.conf /etc/webapp/
COPY requirement /etc/webapp/requirement

WORKDIR /app
COPY src /app

RUN pip install				\
      --no-cache-dir 			\
      --trusted-host pypi.python.org 	\
      # application python requirements:
      -r /etc/webapp/requirement/$TARGET.txt \
      # extas for command-reporting:
      slack-report==0.1.0

CMD supervisord -n -c /etc/supervisor/supervisord.conf

EXPOSE 8000
