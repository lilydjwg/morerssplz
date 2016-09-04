from urllib.parse import urljoin, quote
import datetime
import json
import re
import itertools

import PyRSS2Gen
from tornado import gen, web
from tornado.httpclient import AsyncHTTPClient

from .base import BaseHandler

httpclient = AsyncHTTPClient()

re_br_to_remove = re.compile(r'(?:<br>)+')
re_img = re.compile(r'<img [^>]*?src="([^h])')
re_zhihu_img = re.compile(r'(?<= src=")https://\w+\.zhimg\.com/[^"]+(?=")')

picN = iter(itertools.cycle('1234'))

def proxify_url_cf(match):
  url = match.group()
  return 'https://images.weserv.nl/?url=ssl:' + url[8:]

def proxify_url_google(match):
  url = match.group()
  return 'https://images1-focus-opensocial.googleusercontent.com/gadgets/proxy?url=' + quote(url) + '&container=focus'

PIC_PROXIES = {
  'google': proxify_url_google,
  'cf': proxify_url_cf,
}

def proxify_pic(html, pic):
  html = re_zhihu_img.sub(PIC_PROXIES[pic], html)
  return html

def abs_img(m):
  return '<img src="https://pic%s.zhimg.com/' % next(picN) + m.group(1)

class ZhihuZhuanlanHandler(BaseHandler):
  @gen.coroutine
  def get(self, name):
    pic = self.get_argument('pic', None)
    digest = self.get_argument('digest', False) == 'true'

    baseurl = 'https://zhuanlan.zhihu.com/' + name
    url = 'https://zhuanlan.zhihu.com/api/columns/' + name
    info = yield self._get_url(url)
    url = 'https://zhuanlan.zhihu.com/api/columns/%s/posts?limit=20' % name
    posts = yield self._get_url(url)

    rss = posts2rss(url, info, posts, digest=digest, pic=pic)
    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)

  @gen.coroutine
  def _get_url(self, url):
    res = yield httpclient.fetch(url, raise_error=False)
    if res.code == 404:
      raise web.HTTPError(404)
    else:
      res.rethrow()
    info = json.loads(res.body.decode('utf-8'))
    return info

def parse_time(t):
  t = ''.join(t.rsplit(':', 1))
  return datetime.datetime.strptime(t, '%Y-%m-%dT%H:%M:%S%z')

def process_content(text):
  text = re_br_to_remove.sub(r'', text)
  text = re_img.sub(abs_img, text)
  text = text.replace('<img ', '<img rel="noreferrer" ')
  text = text.replace('<code ', '<pre><code ')
  text = text.replace('</code>', '</code></pre>')
  return text

def post2rss(baseurl, post, *, digest=False, pic=None):
  url = urljoin(baseurl, post['url'])
  if digest:
    content = post['summary']
  elif post.get('titleImage'):
    content = '<p><img src="%s"></p>' % post['titleImage'] + post['content']
  else:
    content = post['content']

  content = process_content(content)
  if pic is not None:
    content = proxify_pic(content, pic)

  item = PyRSS2Gen.RSSItem(
    title = post['title'].replace('\x08', ''),
    link = url,
    description = content,
    pubDate = parse_time(post['publishedTime']),
    author = post['author']['name'],
  )
  return item

def posts2rss(baseurl, info, posts, *, digest=False, pic=None):
  items = [post2rss(baseurl, p, digest=digest, pic=pic) for p in posts]
  rss = PyRSS2Gen.RSS2(
    title = '%s - 知乎专栏' % info['name'],
    link = baseurl,
    lastBuildDate = datetime.datetime.now(),
    items = items,
    generator = 'morerssplz 0.1',
    description = info['description'],
  )
  return rss

def test(url):
  import requests
  column = url.rsplit('/', 1)[-1]

  s = requests.Session()
  s.headers['User-Agent'] = 'curl/7.50.1'
  # s.verify = False
  url = 'https://zhuanlan.zhihu.com/api/columns/' + column
  info = s.get(url).json()
  url = 'https://zhuanlan.zhihu.com/api/columns/%s/posts' % column
  posts = s.get(url).json()

  rss = posts2rss(url, info, posts, pic='cf')
  return rss

if __name__ == '__main__':
  import sys
  test(sys.argv[1]).write_xml(sys.stdout, 'utf-8')
