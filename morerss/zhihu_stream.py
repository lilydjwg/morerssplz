#!/usr/bin/env python3

from urllib.parse import urlencode, urljoin, urlsplit, parse_qs, quote
import json
import datetime
import logging
import re
from functools import partial
import time

from tornado.httpclient import HTTPRequest
import tornado.httpclient
from tornado import gen, web
import PyRSS2Gen
from lxml.html import fromstring, tostring

from . import base

logger = logging.getLogger(__name__)

re_zhihu_img = re.compile(r'https://\w+\.zhimg\.com/.+')
ACCEPT_VERBS = ['MEMBER_CREATE_ARTICLE', 'ANSWER_CREATE']

class ZhihuAPI:
  baseurl = 'https://www.zhihu.com/api/v4/'
  user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:61.0) Gecko/20100101 Firefox/61.0'

  async def activities(self, name):
    url = 'members/%s/activities' % name
    query = {
      'desktop': 'True',
      'after_id': str(int(time.time()) - 86400 * 7),
      'limit': '40',
    }
    url += '?' + urlencode(query)
    data = await self._get_json(url)
    return data

  async def _get_json(self, url):
    req = HTTPRequest(
      urljoin(self.baseurl, url),
      follow_redirects = False,
      headers = {
        'User-Agent': self.user_agent,
        'Authorization': 'oauth c3cef7c66a1843f8b3a9e6a1e3160e20', # hard-coded in js
      },
    )
    res = await base.fetch_zhihu(req)
    return json.loads(res.body.decode('utf-8'))

  async def card(self, name):
    url = 'https://www.zhihu.com/node/MemberProfileCardV2?params=%s' % (quote(
      json.dumps({
        'url_token': name,
      })))
    res = await base.fetch_zhihu(
      url, headers = {'User-Agent': self.user_agent})
    if not res.body:
      # e.g. https://www.zhihu.com/bei-feng-san-dai
      raise web.HTTPError(404)
    doc = fromstring(res.body.decode('utf-8'))
    name = doc.xpath('//span[@class="name"]')[0].text_content()
    url = doc.xpath('//a[@class="avatar-link"]')[0].get('href')

    tagline = doc.xpath('//div[@class="tagline"]')
    if tagline:
      headline = tagline[0].text_content()
    else:
      headline = ''

    return {
      'name': name,
      'headline': headline,
      'url': urljoin('https://www.zhihu.com/', url),
    }

zhihu_api = ZhihuAPI()

async def activities2rss(name, digest=False, pic=None):
  info = await zhihu_api.card(name)
  url = info['url']
  info = {
    'title': '%s - 知乎动态' % info['name'],
    'description': info['headline'],
  }

  data = await zhihu_api.activities(name)
  posts = [x['target'] for x in data['data'] if x['verb'] in ACCEPT_VERBS]
  rss = base.data2rss(
    url,
    info, posts,
    partial(post2rss, digest=digest, pic=pic),
  )
  xml = rss.to_xml(encoding='utf-8')
  return xml

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

def post2rss(post, digest=False, pic=None):
  if post['type'] == 'answer':
    title = '[回答] %s' % post['question']['title']
    url = 'https://www.zhihu.com/question/%s/answer/%s' % (
      post['question']['id'], post['id'])
    t_c = post['created_time']

  elif post['type'] == 'article':
    title = '[文章] %s' % post['title']
    url = 'https://zhuanlan.zhihu.com/p/%s' % post['id']
    t_c = post['created']

  elif post['type'] in ['roundtable', 'live', 'column']:
    return
  else:
    logger.warn('unknown type: %s', post['type'])
    return

  if digest:
    content = post['excerpt']
  else:
    content = post['content']

  content = content.replace('<code ', '<pre><code ')
  content = content.replace('</code>', '</code></pre>')

  doc = fromstring(content)
  tidy_content(doc)
  if pic:
    base.proxify_pic(doc, re_zhihu_img, pic)
  content = tostring(doc, encoding=str)

  pub_date = datetime.datetime.fromtimestamp(t_c)

  item = PyRSS2Gen.RSSItem(
    title = title.replace('\x08', ''),
    link = url,
    description = content.replace('\x08', ''),
    pubDate = pub_date,
    author = post['author']['name'],
  )
  return item

class ZhihuStream(base.BaseHandler):
  @gen.coroutine
  def get(self, name):
    pic = self.get_argument('pic', None)
    digest = self.get_argument('digest', False) == 'true'

    rss = yield activities2rss(name, digest=digest, pic=pic)
    self.finish(rss)

async def test():
  # rss = await activities2rss('cai-qian-hua-56')
  rss = await activities2rss('fu-lan-ke-yang')
  print(rss)

if __name__ == '__main__':
  import tornado.ioloop
  from nicelogger import enable_pretty_logging
  enable_pretty_logging('INFO')
  loop = tornado.ioloop.IOLoop.current()
  loop.run_sync(test)
