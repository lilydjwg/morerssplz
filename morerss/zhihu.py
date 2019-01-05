import datetime
import json
import re
import itertools
from functools import partial

import PyRSS2Gen
from lxml.html import fromstring, tostring

from .base import BaseHandler
from . import base

re_br_to_remove = re.compile(r'(?:<br>)+')
re_img = re.compile(r'<img [^>]*?src="([^h])')
re_zhihu_img = re.compile(r'https://\w+\.zhimg\.com/.+')

picN = iter(itertools.cycle('1234'))

def abs_img(m):
  return '<img src="https://pic%s.zhimg.com/' % next(picN) + m.group(1)

class ZhihuZhuanlanHandler(BaseHandler):
  async def get(self, name):
    pic = self.get_argument('pic', None)
    digest = self.get_argument('digest', False) == 'true'

    baseurl = 'https://zhuanlan.zhihu.com/' + name
    res = await base.fetch_zhihu(baseurl)
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
    res = await base.fetch_zhihu(url)
    info = json.loads(res.body.decode('utf-8'))
    return info

def process_content(text):
  text = re_br_to_remove.sub(r'', text)
  text = re_img.sub(abs_img, text)
  text = text.replace('<img ', '<img referrerpolicy="no-referrer" ')
  text = text.replace('<code ', '<pre><code ')
  text = text.replace('</code>', '</code></pre>')
  return text

def post2rss(baseurl, post, *, digest=False, pic=None):
  url = post['url']
  if digest:
    content = post['excerpt']
  else:
    content = post['excerpt'] + ' (全文尚不可用)'

  if post.get('title_image'):
    content = '<p><img src="%s"></p>' % post['title_image'] + content

  if content:
    content = process_content(content)

    doc = fromstring(content)
    if pic:
      base.proxify_pic(doc, re_zhihu_img, pic)
    content = tostring(doc, encoding=str)

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
