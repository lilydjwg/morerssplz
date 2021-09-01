import json
import datetime
import PyRSS2Gen

from functools import partial
from lxml.html import fromstring, tostring
from tornado import web
from tornado.httpclient import AsyncHTTPClient

from .base import BaseHandler
from . import base

httpclient = AsyncHTTPClient()


def post2rss(post):

  url = f"https://m.okjike.com/originalPosts/{post['id']}"
  date = datetime.datetime.strptime(post['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
  author = post['user']['screenName']
  content = post['content']

  if len(content) > 30:
    title = content[:30]
  else:
    title = content

  description = content + '<br/><br/>'

  for i, picture in enumerate(post['pictures']):
    description += '''<div style="align:left; text-align:center;">
                        <img src="%s" />
                        <div>图 %s/%s</div>
                      </div><br/>''' % (picture.get('thumbnailUrl'), i+1, len(post['pictures']))

  if 'topic' in post:
      topic = post['topic']
      description += "来自圈子：<a href='https://m.okjike.com/topics/%s' target='_blank'>%s</a>" % (topic['id'], topic['content'])

  item = PyRSS2Gen.RSSItem(
    title = title,
    link = url,
    guid = url,
    description = description,
    author = author,
    pubDate = date,
  )

  return item


class JikeUserHandler(base.BaseHandler):
  async def get(self, uid):
    url = f'https://m.okjike.com/users/{uid}'
    webpage = await self._get_url(url)

    doc = fromstring(webpage, base_url=url)
    doc.make_links_absolute()

    data = json.loads(doc.xpath('//script[@type="application/json"]')[0].text_content())['props']['pageProps']

    rss_info = {
      'title': '%s - 即刻用户' % data['user']['screenName'],
      'description': data['user']['briefIntro'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      data['posts'],
      partial(post2rss),
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


class JikeTopicHandler(base.BaseHandler):
  async def get(self, tid):
    url = f'https://m.okjike.com/topics/{tid}'
    webpage = await self._get_url(url)

    doc = fromstring(webpage, base_url=url)
    doc.make_links_absolute()

    data = json.loads(doc.xpath('//script[@type="application/json"]')[0].text_content())['props']['pageProps']

    rss_info = {
      'title': '%s - 即刻圈子' % data['topic']['content'],
      'description': data['topic']['briefIntro'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      data['posts'],
      partial(post2rss),
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
