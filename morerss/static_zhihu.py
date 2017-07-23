import json
import re

from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from lxml.html import fromstring, tostring

from .base import BaseHandler
from .zhihu_stream import tidy_content

httpclient = AsyncHTTPClient()

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

class StaticZhihuHandler(BaseHandler):
  @gen.coroutine
  def get(self, id):
    pic = self.get_argument('pic', None)
    page = yield self._get_url(f'https://zhuanlan.zhihu.com/p/{id}')
    for l in page.splitlines():
      if l.lstrip().startswith('<textarea id="preloadedState" hidden>'):
        content = l.split('>', 1)[-1].rsplit('<', 1)[0]
        content = json.loads(content)
        break

    post = content['database']['Post'][id]
    title = post['title']
    author = post['author']
    body = post['content']
    author = content['database']['User'][author]['name']

    doc = fromstring(body)
    body = tidy_content(doc)
    body = tostring(doc, encoding=str)
    self.set_header('Content-Type', 'text/html; charset=utf-8')
    self.finish(page_template.format_map(vars()))

  @gen.coroutine
  def _get_url(self, url):
    res = yield httpclient.fetch(url, raise_error=False)
    if res.code in [404, 429]:
      raise web.HTTPError(res.code)
    else:
      res.rethrow()
    return res.body.decode('utf-8')
