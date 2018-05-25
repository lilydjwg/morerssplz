import traceback
import http.client
from urllib.parse import quote
import logging
import datetime
import random

from tornado import web, httpclient
from tornado.log import gen_log
from tornado.httpclient import HTTPRequest
import PyRSS2Gen

__version__ = '0.2'
logger = logging.getLogger(__name__)

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
      if err_exc in (None, ' '):
        err_msg = ''
      else:
        if isinstance(err_exc, web.HTTPError):
          if err_exc.log_message is not None:
            err_msg = str(err_exc.log_message) + '.'
          else:
            err_msg = ''
        else:
          err_msg = str(err_exc) + '.'

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
  rss = PyRSS2Gen.RSS2(
    title = info['title'],
    link = url,
    lastBuildDate = datetime.datetime.now(),
    items = items,
    generator = 'morerssplz %s' % (__version__),
    description = info['description'],
  )
  return rss

def _proxify_url_cf(url):
  if url.startswith('http://'):
    url = url[7:]
  elif url.startswith('https://'):
    url = 'ssl:' + url[8:]
  else:
    logger.error('bad image url: %s', url)
    url = url
  return 'https://images.weserv.nl/?url=%s' % url

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

httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
_httpclient = httpclient.AsyncHTTPClient()

try:
  from . import proxy
except ImportError:
  proxy = None

from tornado.options import options
import faker

class ZhihuManager:
  def __init__(self):
    # don't show GET xxx
    from tornado.curl_httpclient import curl_log
    curl_log.setLevel(logging.INFO)
    self.proxies = []
    self.faker = faker.Faker()

  async def _do_fetch(self, url, kwargs):
    if proxy and options.zhihu_proxy:
      return await self._do_fetch_with_proxy(url, kwargs)
    else:
      return await self._do_fetch_direct(url, kwargs)

  async def _do_fetch_direct(self, url, kwargs):
    req = HTTPRequest(url, **kwargs)
    res = await _httpclient.fetch(req, raise_error=False)
    return res

  async def _do_fetch_with_proxy(self, url, kwargs):
    if len(self.proxies) < 10:
      self.proxies.extend([x, 16] for x in (await proxy.get_proxies()))

    p = random.choice(self.proxies)
    logger.debug('Using proxy %s, %d in memory', p, len(self.proxies))
    score = p[1]
    host, port = p[0].rsplit(':', 1)

    req = HTTPRequest(
      url, proxy_host = host, proxy_port = int(port),
      request_timeout = 10,
      **kwargs,
    )

    res = await _httpclient.fetch(req, raise_error=False)
    try:
      if res.code in [599, 403]:
        score >>= 1
      elif res.code == 302 and 'unhuman' in res.headers.get('Location'):
        logger.debug('proxy %s is unhuman-ed by zhihu', p)
        score = 0
      else:
        score += 1

      if score == 0:
        self.proxies.remove(p)
      else:
        p[1] = score
    except ValueError:
      pass # already removed by another request
    return res

  async def fetch_zhihu(self, url, **kwargs):
    kwargs.setdefault('follow_redirects', False)
    kwargs.setdefault('raise_error', False)
    kwargs.setdefault('user_agent', self.faker.user_agent())
    kwargs.pop('raise_error', None)

    res = await self._do_fetch(url, kwargs)

    if res.code in [404, 429]:
      raise web.HTTPError(res.code)
    # 410 in case only logged-in users can see
    # let's return 403 instead
    # 401: suspended account, e.g. hou-xiao-yu-8
    elif res.code in [410, 401]:
      raise web.HTTPError(403)
    elif res.code == 302:
      if 'unhuman' in res.headers.get('Location'):
        raise web.HTTPError(503, 'Rate-limited')
    else:
      res.rethrow()

    return res

fetch_zhihu = ZhihuManager().fetch_zhihu
