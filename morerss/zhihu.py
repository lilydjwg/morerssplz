from urllib.parse import urljoin
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
re_img = re.compile(r'<img src="([^h])')

picN = iter(itertools.cycle('1234'))

def abs_img(m):
  return '<img src="https://pic%s.zhimg.com/' % next(picN) + m.group(1)

class ZhihuZhuanlanHandler(BaseHandler):
  @gen.coroutine
  def get(self, name):
    digest = self.get_argument('digest', False) == 'true'

    baseurl = 'http://zhuanlan.zhihu.com/' + name
    url = 'http://zhuanlan.zhihu.com/api/columns/' + name
    info = yield self._get_url(url)
    url = 'http://zhuanlan.zhihu.com/api/columns/%s/posts?limit=20' % name
    posts = yield self._get_url(url)

    rss = posts2rss(url, info, posts, digest=digest)
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
  return text

def post2rss(baseurl, post, *, digest=False):
  url = urljoin(baseurl, post['url'])
  if digest:
    content = post['summary']
  elif 'titleImage' in post:
    content = '<p><img src="%s"></p>' % post['titleImage'] + post['content']
  else:
    content = post['content']
  item = PyRSS2Gen.RSSItem(
    title = post['title'].replace('\x08', ''),
    link = url,
    description = process_content(content),
    pubDate = parse_time(post['publishedTime']),
    author = post['author']['name'],
  )
  return item

def posts2rss(baseurl, info, posts, *, digest=False):
  items = [post2rss(baseurl, p, digest=digest) for p in posts]
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
  url = 'http://zhuanlan.zhihu.com/api/columns/' + column
  info = s.get(url).json()
  url = 'http://zhuanlan.zhihu.com/api/columns/%s/posts' % column
  posts = s.get(url).json()

  rss = posts2rss(url, info, posts)
  return rss

if __name__ == '__main__':
  import sys
  test(sys.argv[1]).write_xml(sys.stdout, 'utf-8')
