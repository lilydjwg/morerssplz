import logging

from .base import BaseHandler
from .zhihulib import fetch_article

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
    article = await fetch_article(id, pic)

    # used by vars()
    title = article['title']
    author = article['author']['name']
    body = article['content']

    self.set_header('Content-Type', 'text/html; charset=utf-8')
    self.finish(page_template.format_map(vars()))
