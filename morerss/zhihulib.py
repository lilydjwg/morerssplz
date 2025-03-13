import logging
import json
from typing import Optional
from urllib.parse import urlsplit, parse_qs
import re
import itertools

from tornado.options import options, define
from tornado.httpclient import HTTPRequest
from tornado import web, httpclient
from lxml.html import fromstring, tostring

from . import base, pycurl
try:
  from . import proxy
except ImportError:
  proxy = None

_httpclient = httpclient.AsyncHTTPClient()
logger = logging.getLogger(__name__)
re_zhihu_img = re.compile(r'https://\w+\.zhimg\.com/.+')

define("zhihu-proxy", default=False,
        help="use proxies for zhihu", type=bool)

class ZhihuManager:
  def __init__(self):
    # don't show GET xxx
    if pycurl:
      from tornado.curl_httpclient import curl_log
      curl_log.setLevel(logging.INFO)

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
    async with proxy.get_proxy() as p:
      host, port = p.rsplit(':', 1)

      req = HTTPRequest(
        url, proxy_host = host, proxy_port = int(port),
        request_timeout = 10,
        validate_cert = False,
        **kwargs,
      )

      res = await _httpclient.fetch(req, raise_error=False)

      if res.code == 302 and 'unhuman' in res.headers.get('Location'):
        logger.warning('proxy %s is unhuman-ed by zhihu', p)
        raise Exception('unhuman-ed proxy')
      elif res.code == 403:
        res.rethrow()

      return res

  async def fetch_zhihu(self, url, **kwargs):
    if url.startswith('http://'):
      url = 'https://' + url[len('http://'):]
    kwargs.setdefault('follow_redirects', False)
    kwargs.setdefault('user_agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0')
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
    elif res.code == 403:
      if res.body and b'unhuman' in res.body:
        raise web.HTTPError(503, 'Rate-limited')
    # HTTP 301 Moved Permanently
    elif res.code == 301:
      url = res.headers.get('Location')
      res = await self._do_fetch(url, kwargs)
    else:
      if res.error:
        logger.error('error fetching url: %s', url)
        # print(res.headers, res.body and res.body[:100])
      res.rethrow()

    return res

fetch_zhihu = ZhihuManager().fetch_zhihu

def process_content_for_html(body, pic):
  doc = fromstring(body)
  tidy_content(doc)
  if pic:
    base.proxify_pic(doc, re_zhihu_img, pic)
  return tostring(doc, encoding=str)

re_br_to_remove = re.compile(r'(?:<br>)+')
re_img = re.compile(r'<img [^>]*?src="([^h])')
re_zhihu_img = re.compile(r'https://\w+\.zhimg\.com/.+')

_picN = iter(itertools.cycle('1234'))

def _abs_img(m):
  return '<img src="https://pic%s.zhimg.com/' % next(_picN) + m.group(1)

def process_content_for_rss(body, pic):
  body = re_br_to_remove.sub(r'', body)
  body = re_img.sub(_abs_img, body)
  body = body.replace('<img ', '<img referrerpolicy="no-referrer" ')
  body = body.replace('<code ', '<pre><code ')
  body = body.replace('</code>', '</code></pre>')

  doc = fromstring(body)
  if pic:
    base.proxify_pic(doc, re_zhihu_img, pic)
  return tostring(doc, encoding=str)

async def fetch_article(id: str, pic: Optional[str],
                        processor=process_content_for_html):
  url = f'https://zhuanlan.zhihu.com/p/{id}'
  res = await fetch_zhihu(url)
  page = res.body.decode('utf-8')

  doc = fromstring(page)
  try:
    static = doc.xpath('//script[@id="js-initialData"]')[0]
  except IndexError:
    logger.error('page source: %s', page)
    raise
  content = json.loads(static.text)['initialState']

  article = content['entities']['articles'][id]
  article['content'] = processor(article['content'], pic=pic)
  return article

def tidy_content(doc):
  for br in doc.xpath('//p/following-sibling::br'):
    br.getparent().remove(br)

  for noscript in doc.xpath('//noscript'):
    p = noscript.getparent()
    img = noscript.getnext()
    if img.tag == 'img':
      p.remove(img)
    p.replace(noscript, noscript[0])

  for img in doc.xpath('//img[@src]'):
    attrib = img.attrib
    attrib['referrerpolicy'] = 'no-referrer'
    if 'data-original' in attrib:
      img.set('src', attrib['data-original'])
      del attrib['data-original']

    if 'class' in attrib:
      del attrib['class']
    if 'data-rawwidth' in attrib:
      del attrib['data-rawwidth']
    if 'data-rawheight' in attrib:
      del attrib['data-rawheight']

  for a in doc.xpath('//a[starts-with(@href, "https://link.zhihu.com/?target=")]'):
    href = a.get('href')
    href = parse_qs(urlsplit(href).query)['target'][0]
    a.set('href', href)

  for a in doc.xpath('//a[starts-with(@href, "https://link.zhihu.com/?target=")]'):
    href = a.get('href')
    href = parse_qs(urlsplit(href).query)['target'][0]
    a.set('href', href)

  for a in doc.xpath('//a'):
    for k in ['rel', 'class']:
      try:
        del a.attrib[k]
      except KeyError:
        pass

