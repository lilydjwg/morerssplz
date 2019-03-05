from functools import partial

import PyRSS2Gen
from tornado import web
from tornado.httpclient import AsyncHTTPClient
from lxml.html import fromstring, tostring

from .base import BaseHandler
from . import base

httpclient = AsyncHTTPClient()

class V2exCommentHandler(BaseHandler):
  async def get(self, tid):
    url = 'https://www.v2ex.com/t/' + tid
    webpage = await self._get_url(url)

    try:
      data = parse_webpage(webpage, baseurl=url)

      if len(data['comments']) < 40 and data['prev']:
        webpage = await self._get_url(data['prev'])
        data2 = parse_webpage(webpage, baseurl=data['prev'])
        comments = data['comments'] + data2['comments']
        if len(comments) > 40:
          comments = comments[:40]
      else:
        comments = data['comments']
    except PermissionError:
      raise web.HTTPError(403, 'login required')

    rss_info = {
      'title': '[评论] %s' % data['subject'],
      'description': data['description'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      comments,
      partial(comment2rss, url),
    )
    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)

  async def _get_url(self, url):
    res = await httpclient.fetch(url, raise_error=False)
    if res.code in [404, 429]:
      raise web.HTTPError(res.code)
    else:
      res.rethrow()
    return res.body.decode('utf-8')

def comment2rss(url, comment):
  rid = comment.get('id')
  url = '%s#%s' % (url, rid)
  content = comment.xpath('.//div[@class="reply_content"]')[0]
  author = comment.xpath('.//strong/a')[0].text
  content_text = content.text_content()
  if len(content_text) > 30:
    title = "%s 说: %s……" % (author, content_text[:30])
  else:
    title = "%s 说: %s" % (author, content_text)

  content = tostring(content, encoding=str).strip().replace('\r', '')

  item = PyRSS2Gen.RSSItem(
    title = title,
    link = url,
    guid = url,
    description = content,
    author = author,
  )
  return item

def parse_webpage(body, baseurl):
  doc = fromstring(body, base_url=baseurl)
  doc.make_links_absolute()
  subject = doc.xpath('//title')[0].text_content()
  if subject == 'V2EX › 登录':
    raise PermissionError

  description = doc.xpath('//meta[@property="og:description"]')[0] \
      .get('content')
  comments = doc.xpath('//div[@id="Main"]/div[@class="box"]/div[@id]')
  comments = comments[-40:]
  comments.reverse()
  prev = doc.xpath('//link[@rel="prev"]')
  if prev:
    prev = prev[0].get('href')
  else:
    prev = None

  return {
    'subject': subject,
    'description': description,
    'comments': comments,
    'prev': prev,
  }

def test():
  import requests

  s = requests.Session()
  # s.verify = False
  url = 'https://www.v2ex.com/t/350434'
  r = s.get(url)
  data = parse_webpage(r.text, baseurl=url)

  rss_info = {
    'title': '[评论] %s' % data['subject'],
    'description': data['description'],
  }
  rss = base.data2rss(
    url,
    rss_info,
    data['comments'],
    partial(comment2rss, url),
  )
  return rss

if __name__ == '__main__':
  import sys
  test().write_xml(sys.stdout, 'utf-8')
