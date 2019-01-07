import datetime
import json
from functools import partial
import re
import asyncio
import os
import logging
import time

import PyRSS2Gen
from lxml.html import fromstring, tostring
from tornado.options import options, define

from .base import BaseHandler
from . import base
from . import zhihulib

logger = logging.getLogger(__name__)
define("cache-dir", default='/tmp/rss-cache',
       help="cache directory for RSS data", type=str)

_article_q = asyncio.Queue(maxsize=30)

def _save_article(doc):
  fname = '{}-{}.json'.format(doc['id'], doc['updated'])
  with open(os.path.join(options.cache_dir, fname), 'w') as f:
    json.dump(doc, f, ensure_ascii=False)

async def _article_fetcher():
  os.makedirs(options.cache_dir, exist_ok=True)
  while True:
    try:
      id = await _article_q.get()
      logger.info('fetching zhihu article %s', id)
      article = await zhihulib.fetch_article(id, pic=None)
      _save_article(article)
      _article_q.task_done()
    except Exception:
      logger.exception('error in _article_fetcher, sleeping 1s.')
      time.sleep(1)

def article_from_cache(id, updated):
  fname = '{}-{}.json'.format(id, updated)
  try:
    with open(os.path.join(options.cache_dir, fname)) as f:
      return json.load(f)
  except FileNotFoundError:
    return None

class ZhihuZhuanlanHandler(BaseHandler):
  async def get(self, name):
    pic = self.get_argument('pic', None)
    digest = self.get_argument('digest', False) == 'true'

    baseurl = 'https://zhuanlan.zhihu.com/' + name
    res = await zhihulib.fetch_zhihu(baseurl)
    if res.code == 302:
      new_name = res.headers['Location'].rsplit('/', 1)[-1]
      url = self.request.uri
      self.redirect(re.sub(f'/{re.escape(name)}\\b', f'/{new_name}', url))
      return

    url = 'https://zhuanlan.zhihu.com/api2/columns/{}/articles?limit=20&include=data%5B*%5D.admin_closed_comment%2Ccomment_count%2Csuggest_edit%2Cis_title_image_full_screen%2Ccan_comment%2Cupvoted_followees%2Ccan_open_tipjar%2Ccan_tip%2Cvoteup_count%2Cvoting%2Ctopics%2Creview_info%2Cauthor.is_following%2Cis_labeled%2Clabel_info'.format(name)
    posts = await self._get_url(url)

    doc = fromstring(res.body.decode('utf-8'))
    name = doc.xpath('//h1[@class="ColumnHeader-Title"]')[0].text_content()
    description = doc.xpath('//p[@class="ColumnHeader-Desc"]')[0].text_content()
    rss_info = {
      'title': '%s - 知乎专栏' % name,
      'description': description,
    }

    rss = base.data2rss(
      baseurl,
      rss_info, posts['data'],
      partial(post2rss, url, digest=digest, pic=pic),
    )
    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)

  async def _get_url(self, url):
    res = await zhihulib.fetch_zhihu(url)
    info = json.loads(res.body.decode('utf-8'))
    return info

def post2rss(baseurl, post, *, digest=False, pic=None):
  url = post['url']
  if digest:
    content = post['excerpt']
    content = zhihulib.process_content_for_html(content, pic=pic)
  else:
    article = article_from_cache(post['id'], post['updated'])
    if not article:
      content = post['excerpt'] + ' (全文尚不可用)'
      content = zhihulib.process_content_for_html(content, pic=pic)
      try:
        _article_q.put_nowait(str(post['id']))
      except asyncio.QueueFull:
        logger.warning('_article_q full')
    else:
      content = article['content']
      if pic:
        doc = fromstring(content)
        base.proxify_pic(doc, zhihulib.re_zhihu_img, pic)
        content = tostring(doc, encoding=str)

  if post.get('title_image'):
    content = '<p><img src="%s"></p>' % post['title_image'] + content

  item = PyRSS2Gen.RSSItem(
    title = post['title'].replace('\x08', ''),
    link = url,
    description = content,
    pubDate = datetime.datetime.fromtimestamp(post['created']),
    author = post['author']['name'],
  )
  return item

def test(url):
  import requests
  column = url.rsplit('/', 1)[-1]
  baseurl = url

  s = requests.Session()
  s.headers['User-Agent'] = 'curl/7.50.1'
  # s.verify = False
  url = 'https://zhuanlan.zhihu.com/api/columns/' + column
  info = s.get(url).json()
  url = 'https://zhuanlan.zhihu.com/api/columns/%s/posts' % column
  posts = s.get(url).json()

  rss_info = {
    'title': '%s - 知乎专栏' % info['name'],
    'description': info.get('description', ''),
  }
  rss = base.data2rss(
    baseurl,
    rss_info, posts,
    partial(post2rss, url, pic='cf'),
  )
  return rss

if __name__ == '__main__':
  import sys
  test(sys.argv[1]).write_xml(sys.stdout, 'utf-8')
