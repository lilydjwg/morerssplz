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


class MattersAPI:
  endpoint = 'https://server.matters.news/graphql'
  user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0'

  async def _get_json(self, query):
    headers = {
      'User-Agent': self.user_agent,
      'Content-Type': 'application/json',
    }

    res = await httpclient.fetch(self.endpoint, raise_error=False, headers=headers,
                                 method='POST', body=json.dumps({'query':query}))

    if res.code in [404, 429]:
      raise web.HTTPError(res.code)
    else:
      res.rethrow()

    return json.loads(res.body.decode('utf-8'))

  async def get_articles_by_user(self, uid):

    query = """
      query {
        user(input: { userName: "%s" }) {
          displayName
          info {
            description
          }
          articles(input: { first: 20 }) {
            edges {
              node {
                author {
                  userName
                  displayName
                }
                access{ type }
                slug
                mediaHash
                title
                summary
                content
                createdAt
              }
            }
          }
        }
      }""" % uid

    res = await self._get_json(query)
    return res['data']

  async def get_articles_by_topic(self, tid, article_type):

    query = """
      query {
        node(input: { id: "%s" }) {
          ... on Tag {
            id
            content
            description
            articles(input: { first: 10, selected: %s }) {
              edges {
                node {
                  author {
                    displayName
                    userName
                  }
                  summary
                  access{ type }
                  slug
                  mediaHash
                  title
                  content
                  createdAt
                }
              }
            }
          }
        }
      }""" % (tid, 'false' if article_type != 'selected' else 'true')

    res = await self._get_json(query)
    return res['data']


matters_api = MattersAPI()


def article2rss(node):
  article = node['node']

  if article['access']['type'] == 'public':
    article_type = '公开'
  elif article['access']['type'] == 'paywall':
    article_type = '付费'
  else:
    article_type = '未知'

  url = f'https://matters.news/@{article["author"]["userName"]}/{article["slug"]}-{article["mediaHash"]}'

  item = PyRSS2Gen.RSSItem(
    title=f"[{article_type}] {article['title']}",
    link=url,
    guid=url,
    description=article['summary'] + '<br/>'*2 + article['content'],
    author=article['author']['displayName'],
    pubDate=article['createdAt'],
  )

  return item


class MattersUserArticleHandler(base.BaseHandler):
  async def get(self, uid):
    url = f'https://matters.news/@{uid}/'

    data = await matters_api.get_articles_by_user(uid)

    rss_info = {
      'title': '%s - Matters 用户文章' % data['user']['displayName'],
      'description': data['user']['info']['description'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      data['user']['articles']['edges'],
      partial(article2rss),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)


class MattersTopicHandler(base.BaseHandler):
  async def get(self, tid):
    url = f'https://matters.news/tags/{tid}'

    article_type = self.get_argument('type', None)
    if article_type not in ('latest', 'selected'):
      article_type = 'latest'

    data = await matters_api.get_articles_by_topic(tid, article_type)

    rss_info = {
      'title': '%s - %s - Matters 标签' % (data['node']['content'],'最新' if article_type != 'selected' else '精选'),
      'description': data['node']['description'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      data['node']['articles']['edges'],
      partial(article2rss),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)
