from urllib.parse import urlencode, urljoin, quote
import json
import datetime
import logging
from functools import partial
import time

import tornado.httpclient
from tornado import web
import PyRSS2Gen
from lxml.html import fromstring, tostring

from . import base
from .zhihulib import fetch_zhihu, re_zhihu_img, tidy_content

logger = logging.getLogger(__name__)

ACCEPT_VERBS = ['MEMBER_CREATE_ARTICLE', 'ANSWER_CREATE']

class ZhihuAPI:
  baseurl = 'https://www.zhihu.com/api/v4/'
  user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0'

  async def activities(self, name):
    url = 'members/%s/activities' % name
    query = {
      'desktop': 'True',
      'after_id': str(int(time.time())),
      'limit': '7',
    }
    url += '?' + urlencode(query)
    data = await self.get_json(url)
    return data

  async def get_json(self, url):
    url = urljoin(self.baseurl, url)
    headers = {
      'User-Agent': self.user_agent,
      'Authorization': 'oauth c3cef7c66a1843f8b3a9e6a1e3160e20', # hard-coded in js
      'x-api-version': '3.0.40',
      'x-udid': 'AMAiMrPqqQ2PTnOxAr5M71LCh-dIQ8kkYvw=',
    }
    res = await fetch_zhihu(url, headers = headers)
    return json.loads(res.body.decode('utf-8'))

  async def card(self, name):
    url = 'https://www.zhihu.com/node/MemberProfileCardV2?params=%s' % (quote(
      json.dumps({
        'url_token': name,
      })))
    res = await fetch_zhihu(
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

  posts = []
  page = 0

  data = await zhihu_api.activities(name)
  posts = [x['target'] for x in data['data'] if x['verb'] in ACCEPT_VERBS]

  while len(posts) < 20 and page < 3:
    paging = data['paging']
    # logger.debug('paging: %r', paging)
    if paging['is_end']:
      break
    data = await zhihu_api.get_json(paging['next'])
    posts.extend(
      x['target'] for x in data['data'] if x['verb'] in ACCEPT_VERBS
    )
    page += 1

  rss = base.data2rss(
    url,
    info, posts,
    partial(post2rss, digest=digest, pic=pic),
  )
  xml = rss.to_xml(encoding='utf-8')
  return xml

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

  pub_date = datetime.datetime.utcfromtimestamp(t_c)

  item = PyRSS2Gen.RSSItem(
    title = title.replace('\x08', ''),
    link = url,
    guid = url,
    description = content.replace('\x08', ''),
    pubDate = pub_date,
    author = post['author']['name'],
  )
  return item

class ZhihuStream(base.BaseHandler):
  async def get(self, name):
    if name.endswith(' '):
      raise web.HTTPError(404)
    pic = self.get_argument('pic', None)
    digest = self.get_argument('digest', False) == 'true'

    rss = await activities2rss(name, digest=digest, pic=pic)
    self.finish(rss)

async def test():
  # rss = await activities2rss('cai-qian-hua-56')
  rss = await activities2rss('farseerfc')
  print(rss)

if __name__ == '__main__':
  import tornado.ioloop
  from nicelogger import enable_pretty_logging
  enable_pretty_logging('DEBUG')
  loop = tornado.ioloop.IOLoop.current()
  loop.run_sync(test)
