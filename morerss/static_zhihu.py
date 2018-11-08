import json
import logging

from lxml.html import fromstring, tostring

from . import base
from .base import BaseHandler, fetch_zhihu
from .zhihu_stream import tidy_content, re_zhihu_img

page_template = '''\
<!DOCTYPE html>
<meta charset="utf-8" />
<meta name="referrer" value="no-referrer" />
<title>{title} - {author}</title>
<style type="text/css">
body {{ max-width: 700px; margin: auto; }}
</style>
<h2>{title}</h2>
<h3>作者: {author}</h3>
{body}
<hr/>
<footer><a href="https://zhuanlan.zhihu.com/p/{id}">原文链接</a></footer>
'''

logger = logging.getLogger(__name__)

class StaticZhihuHandler(BaseHandler):
  async def get(self, id):
    pic = self.get_argument('pic', None)
    page = await self._get_url(f'https://zhuanlan.zhihu.com/p/{id}')
    doc = fromstring(page)
    try:
      static = doc.xpath('//script[@id="js-initialData"]')[0]
    except IndexError:
      logger.error('page source: %s', page)
      raise
    content = json.loads(static.text)['initialState']

    article = content['entities']['articles'][id]
    # used by vars()
    title = article['title']
    author = article['author']['name']
    body = article['content']

    doc = fromstring(body)
    body = tidy_content(doc)

    if pic:
      base.proxify_pic(doc, re_zhihu_img, pic)

    body = tostring(doc, encoding=str)
    self.set_header('Content-Type', 'text/html; charset=utf-8')
    self.finish(page_template.format_map(vars()))

  async def _get_url(self, url):
    res = await fetch_zhihu(url)
    return res.body.decode('utf-8')
