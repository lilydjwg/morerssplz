import traceback
import http.client
from urllib.parse import quote
import logging
import datetime

from tornado import web, httpclient
from tornado.log import gen_log
import PyRSS2Gen
import statsd

__version__ = '0.4'
logger = logging.getLogger(__name__)
STATSC = statsd.StatsClient('localhost', 8125, prefix='morerss')

class BaseHandler(web.RequestHandler):
  error_page = '''\
<!DOCTYPE html>
<meta charset="utf-8" />
<title>%(code)s %(message)s</title>
<style type="text/css">
  body { font-family: serif; }
</style>
<h1>%(code)s %(message)s</h1>
<p>%(err)s</p>
<hr/>
'''

  def initialize(self):
    self.set_header('Content-Type', 'application/rss+xml; charset=utf-8')
    self.set_header('Cache-Control', 'public, max-age=14400')

  def write_error(self, status_code, **kwargs):
    if self.settings.get("debug") and "exc_info" in kwargs:
      # in debug mode, try to send a traceback
      self.set_header('Content-Type', 'text/plain')
      for line in traceback.format_exception(*kwargs["exc_info"]):
        self.write(line)
      self.finish()
    else:
      err_exc = kwargs.get('exc_info', '  ')[1]
      if (err_exc not in (None, ' ') and isinstance(err_exc, web.HTTPError)
          and err_exc.log_message is not None):
        err_msg = f'{str(err_exc.log_message)}.'
      elif (err_exc not in (None, ' ') and isinstance(err_exc, web.HTTPError)
            or err_exc in (None, ' ')):
        err_msg = ''
      else:
        err_msg = f'{str(err_exc)}.'

      if status_code in [302, 400, 403, 404, 405]:
        # cache some errors
        self.set_header('Cache-Control', 'public, max-age=14400')

      self.finish(self.error_page % {
        "code": status_code,
        "message": http.client.responses[status_code],
        "err": err_msg,
      })

  def log_exception(self, typ, value, tb):
    if isinstance(value, httpclient.HTTPError) and value.code >= 500:
      gen_log.warning('client error: %r', value)
    else:
      super().log_exception(typ, value, tb)

def data2rss(url, info, data, transform_func):
  items = [transform_func(x) for x in data]
  items = [x for x in items if x]
  return PyRSS2Gen.RSS2(
      title=info['title'],
      link=url,
      lastBuildDate=datetime.datetime.now(),
      items=items,
      generator=f'morerssplz {__version__}',
      description=info['description'],
  )

def _proxify_url_cf(url):
  if url.startswith('http://'):
    url = url[7:]
  elif url.startswith('https://'):
    url = f'ssl:{url[8:]}'
  else:
    logger.error('bad image url: %s', url)
    url = url
  return f'https://images.weserv.nl/?url={url}'

def _proxify_url_google(url):
  return 'https://images1-focus-opensocial.googleusercontent.com/gadgets/proxy?url=' + quote(url) + '&container=focus'

PIC_PROXIES = {
  'google': _proxify_url_google,
  'cf': _proxify_url_cf,
}

def proxify_pic(doc, pattern, pic):
  p = PIC_PROXIES[pic]
  for img in doc.xpath('//img[@src]'):
    src = img.get('src')
    if pattern.match(src):
      img.set('src', p(src))

class MyApp(web.Application):
  def log_request(self, handler):
    super().log_request(handler)

    code = handler.get_status()
    request_time = 1000.0 * handler.request.request_time()
    STATSC.timing(f'handler.{handler.__class__.__name__}.{code}', request_time)
