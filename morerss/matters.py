import json
import datetime
import PyRSS2Gen

from functools import partial
from lxml.html import fromstring, tostring
from tornado import web
from tornado.httpclient import AsyncHTTPClient

from .base import BaseHandler
from . import base


endpoint = 'https://server.matters.news/graphql'
httpclient = AsyncHTTPClient()


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

    result = await self._get_url(query)
    data = json.loads(result)['data']

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

  async def _get_url(self, query):
    res = await httpclient.fetch(endpoint, raise_error=False,
                                 method='POST', body=json.dumps({'query':query}),
                                 headers={'Content-Type': 'application/json'})

    if res.code in [404, 429]:
      raise web.HTTPError(res.code)
    else:
      res.rethrow()

    return res.body.decode('utf-8')


class MattersTopicHandler(base.BaseHandler):
  async def get(self, tid):
    url = f'https://matters.news/tags/{tid}'

    article_type = self.get_argument('type', None)
    if article_type not in ('latest', 'selected'):
      article_type = 'latest'

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

    result = await self._get_url(query)
    data = json.loads(result)['data']

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

  async def _get_url(self, query):
    res = await httpclient.fetch(endpoint, raise_error=False,
                                 method='POST', body=json.dumps({'query':query}),
                                 headers={'Content-Type': 'application/json'})

    if res.code in [404, 429]:
      raise web.HTTPError(res.code)
    else:
      res.rethrow()

    return res.body.decode('utf-8')
