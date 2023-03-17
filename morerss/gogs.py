import datetime

import PyRSS2Gen
from tornado import web
from tornado.httpclient import AsyncHTTPClient
from lxml.html import fromstring, tostring

from .base import BaseHandler
from . import base

httpclient = AsyncHTTPClient()

class GogsIssueHandler(BaseHandler):
  async def get(self, host, user, repo, nr):
    url = f'https://{host}/{user}/{repo}/issues/{nr}'
    webpage = await self._get_url(url)

    doc = fromstring(webpage, base_url=url)
    doc.make_links_absolute()
    title = doc.get_element_by_id('issue-title').text_content()
    description = doc.xpath('//meta[@name="description"]')[0].get('content')
    messages = doc.xpath('//ui/div[@class="comment"]')

    rss_info = {
      'title': f'{title} - {user}/{repo} - {host}',
      'description': description,
    }

    rss = base.data2rss(
      url,
      rss_info,
      messages,
      message_proc,
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

def message_proc(message):
  author_link, anchor = message.xpath('div/div/span/a')
  author = author_link.text_content()
  url = anchor.get('href')

  date = anchor[0].get('title')
  date = datetime.datetime.strptime(date, '%a, %d %b %Y %H:%M:%S %Z')

  content = message.xpath('.//div[starts-with(@class, "render-content")]')[0]
  text = content.text_content().strip()
  content = tostring(content, encoding=str)

  text = text.split('\n', 1)[0]
  if len(text) > 150:
    text = text[:150] + '…'
  title = f'{author}: {text}'

  item = PyRSS2Gen.RSSItem(
    title = title,
    link = url,
    guid = url,
    description = content,
    author = author,
    pubDate = date,
  )
  return item
