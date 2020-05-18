from functools import partial
import datetime

import PyRSS2Gen
from tornado import web
from tornado.httpclient import AsyncHTTPClient
from lxml.html import fromstring, tostring, Element

from .base import BaseHandler
from . import base

httpclient = AsyncHTTPClient()

class TGChannelHandler(BaseHandler):
  async def get(self, channel):
    url = f'https://t.me/s/{channel}'
    webpage = await self._get_url(url)

    doc = fromstring(webpage, base_url=url)
    doc.make_links_absolute()
    title = doc.xpath('//meta[@property="og:title"]')[0].get('content')
    description = doc.xpath('//meta[@property="og:description"]')[0].get('content')
    messages = doc.xpath('//div[@data-post]')[::-1]

    rss_info = {
      'title': title,
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
  url = f"https://t.me/s/{message.get('data-post')}"

  author = message.xpath('.//span[@class="tgme_widget_message_from_author"]') or ''
  if author:
    author = author[0].text_content()

  date = message.xpath('.//a[@class="tgme_widget_message_date"]/time')[0]
  date = datetime.datetime.fromisoformat(date.get('datetime'))

  text = message.xpath('.//div[starts-with(@class, "tgme_widget_message_text ")]')[0]
  del text.attrib['class']
  content = tostring(text, encoding=str).strip().replace('\r', '')

  reply = message.xpath('.//a[@class="tgme_widget_message_reply"]')
  if reply:
    reply = reply[0]
    reply.tag = 'div'
    reply[0].tag = 'a'
    reply[0].set('href', reply.get('href').replace('https://t.me/', 'https://t.me/s/'))
    del reply.attrib['href']
    content = "<blockquote>%s</blockquote>" % tostring(reply, encoding=str).strip().replace('\r', '') + content

  linkpreview = message.xpath('.//a[@class="tgme_widget_message_link_preview"]')
  if linkpreview:
    linkpreview = linkpreview[0]
    linkpreview.tag = 'div'

    sitename = linkpreview.xpath('.//div[@class="link_preview_site_name"]')[0]
    sitediv = Element('div')
    sitestrong = Element('strong')
    sitestrong.text = sitename.text_content()
    sitediv.append(sitestrong)
    sitename.getparent().replace(sitename, sitediv)

    previewtitle = linkpreview.xpath('.//div[@class="link_preview_title"]')[0]
    previewtitle.tag = 'a'
    previewtitle.set('href', linkpreview.get('href'))
    del linkpreview.attrib['href']
    image = linkpreview.xpath('.//i[@class="link_preview_right_image"]')
    if image:
      image = image[0]
      image.tag = 'img'
      image.set('src', image.attrib.pop('style').split("'")[1])
      image.set('style', 'max-height: 5em;')
    content += "<blockquote>%s</blockquote>" % tostring(linkpreview, encoding=str).strip().replace('\r', '')

  content_text = text.text_content()
  if len(content_text) > 30:
    title = "%s……" % (content_text[:30])
  else:
    title = content_text

  item = PyRSS2Gen.RSSItem(
    title = title,
    link = url,
    guid = url,
    description = content,
    author = author,
    pubDate = date,
  )
  return item
