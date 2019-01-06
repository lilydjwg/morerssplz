import logging
import random

from tornado.options import options
from tornado.httpclient import HTTPRequest
from tornado import web, httpclient

try:
  from . import proxy
except ImportError:
  proxy = None

_httpclient = httpclient.AsyncHTTPClient()
logger = logging.getLogger(__name__)

class ZhihuManager:
  def __init__(self):
    # don't show GET xxx
    from tornado.curl_httpclient import curl_log
    curl_log.setLevel(logging.INFO)
    self.proxies = []

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
    kwargs.setdefault('user_agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0')
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

