FROM python:3-alpine
MAINTAINER beyondblog <beyondblog@outlook.com>

RUN set -ex \
    && apk add --no-cache --virtual .fetch-deps \
            gcc \
            libc-dev    \
            libxslt-dev \
            libxml2-dev \
    && pip3 install tornado lxml PyRSS2Gen statsd

EXPOSE 8000

WORKDIR morerssplz

ADD ./ /morerssplz

CMD ["/morerssplz/main.py"]

