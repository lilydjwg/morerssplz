import json
import datetime
import PyRSS2Gen

from datetime import datetime
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

  article_fragment = """
    fragment ArticleFeed on Article {
      id
      title
      slug
      mediaHash
      summary
      content
      createdAt
      author {
        userName
        displayName
      }
      access { type }
      __typename
    }
  """

  comment_fragment = """
    fragment CommentFeed on Comment {
      id
      content
      createdAt
      author {
        id
        userName
        displayName
      }
      __typename
    }
  """

  nested_comment_fragment = """
    fragment NestedCommentFeed on Comment {
      ...CommentFeed

      replyTo { ...CommentFeed }

      parentComment { id }

      node { ...ArticleFeed }
    }
  """

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

  async def get_feed(self, feed_type):
    query = """
      query {
        viewer {
          id
          recommendation {
            feed: %s (input: { first: 10 }) {
              edges {
                node {
                  ...ArticleFeed
                }
              }
            }
          }
        }
      }

      %s
    """ % (feed_type, self.article_fragment)

    res = await self._get_json(query)
    return res['data']['viewer']['recommendation']['feed']

  async def get_articles_by_circle(self, cname):

    query = """
      query {
        circle(input: { name: "%s" }) {
          id
          displayName
          description
          articles: works(input: { first: 5 }) {
            edges {
              node {
                ...ArticleFeed
              }
            }
          }
        }
      }

      %s
    """ % (cname, self.article_fragment)

    res = await self._get_json(query)
    return res['data']

  async def get_articles_by_user(self, uname):

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
                ...ArticleFeed
              }
            }
          }
        }
      }

      %s
    """ % (uname, self.article_fragment)

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
                  ...ArticleFeed
                }
              }
            }
          }
        }
      }

      %s
    """ % (tid, 'false' if article_type != 'selected' else 'true', self.article_fragment)

    res = await self._get_json(query)
    return res['data']

  async def get_broadcast_by_circle(self, cname):
    query = """
      query {
        circle(input: { name: "%s" }) {
          id
          displayName
          description

          broadcast(input: { first: 10 }) {
            edges {
              node {
                ...ThreadCommentCommentPublic
              }
            }
          }
        }
      }

      fragment ThreadCommentCommentPublic on Comment {
        id
        ...NestedCommentFeed

        comments(input: { sort: oldest, first: null }) {
          edges {
            node {
              ...NestedCommentFeed
            }
          }
        }
      }

      %s

      %s

      %s
    """ % (cname, self.nested_comment_fragment,
           self.comment_fragment, self.article_fragment)
    res = await self._get_json(query)

    for edge in res['data']['circle']['broadcast']['edges']:
      edge['node']['__typename'] = 'Broadcast'

    return res['data']

  async def get_comments_by_user(self, uid):
    query = """
      query {
        node(input: { id: "%s" }) {
          ... on User {
            commentedArticles(input: { first: 5 }) {
              edges {
                node {
                  comments(input: { filter: { author: "%s" }, first: null }) {
                    edges {
                      node {
                        ...NestedCommentFeed
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }

      %s

      %s

      %s
    """ % (uid, uid, self.nested_comment_fragment,
           self.comment_fragment, self.article_fragment)

    res = await self._get_json(query)
    return res['data']['node']

  async def get_user_by_name(self, uname):
    query = """
      query {
        user(input: { userName: "%s" }) {
          id
          userName
          displayName
          info {
            description
          }
        }
      }
    """ % uname

    res = await self._get_json(query)
    return res['data']


matters_api = MattersAPI()


def edge2rssitem(edge):
  item = None
  typename = edge['node']['__typename'].lower()

  if typename == 'article':
    item = article2rssitem(edge)
  elif typename == 'comment' or typename == 'broadcast':
    item = comment2rssitem(edge)
  else:
    item = PyRSS2Gen.RSSItem(
      title=f'未支持的类型：{typename}',
      link='',
      guid='',
      description=f'未支持的类型：{typename}',
      author='',
      pubDate=datetime.now(),
    )

  return item


def article2rssitem(edge):
  article = edge['node']

  if article['access']['type'] == 'public':
    article_type = '公开作品'
  elif article['access']['type'] == 'paywall':
    article_type = '付费作品'
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


def comment2rssitem(edge):
  comment = edge['node']

  author_url = f'https://matters.news/@{comment["author"]["userName"]}'
  comment_url = ''

  content = """
    <div>%s</div>
    <p>%s</p>
  """ % (comment['content'],
         datetime.strptime(comment['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%d-%m %H:%M:%S'))

  article = comment['node']
  if article:
    article_url = f'https://matters.news/@{article["author"]["userName"]}/{article["slug"]}-{article["mediaHash"]}'
    article_info = """
      <div><a href='%s'>%s</a> 在 <a href='%s'>《%s》</a> 下的评论</div>
    """ % (author_url, comment['author']['displayName'],
           article_url, article['title'])

    content = article_info + content

    if comment['parentComment']:
      comment_url = f'{article_url}#{comment["parentComment"]["id"]}-{comment["id"]}'
    else:
      comment_url = f'{article_url}#{comment["id"]}'

  if comment['replyTo']:
    author_url = f'https://matters.news/@{comment["replyTo"]["author"]["userName"]}'
    reply_to_content = """
      <blockquote>
        <p>回复： <a href='%s'>%s</a></p>
        <div>%s</div>
        <p>%s</p>
      </blockquote>
    """ % (author_url, comment['replyTo']['author']['displayName'],
           comment['replyTo']['content'],
           datetime.strptime(comment['replyTo']['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%d-%m %H:%M:%S'))
    content += reply_to_content

  comment_type = comment['__typename']
  if comment['__typename'].lower() == 'comment':
    comment_type = '评论'
  elif comment['__typename'].lower() == 'broadcast':
    comment_type = '广播'

  import re
  title = re.sub('<p>|</p>', '',
                 re.split(r'[,，\.。;；!！\?？~]|<br/>', comment['content'])[0])
  item = PyRSS2Gen.RSSItem(
    title=f'[{comment_type}] {title}',
    link=comment_url,
    guid=comment_url,
    description=content,
    author=comment['author']['displayName'],
    pubDate=comment['createdAt'],
  )

  return item


class MattersCircleHandler(base.BaseHandler):
  async def get(self, cname):
    url = f'https://matters.news/~{cname}'

    is_article = self.get_argument('article', '1')
    is_broadcast = self.get_argument('broadcast', '1')

    circle = None
    edges = []

    if is_article == '1':
      data = await matters_api.get_articles_by_circle(cname)
      circle = data['circle']
      edges.extend(circle['articles']['edges'])

    if is_broadcast == '1':
      data = await matters_api.get_broadcast_by_circle(cname)
      circle = data['circle']
      edges.extend(circle['broadcast']['edges'])

    if circle:
      rss_info = {
        'title': '%s - Matters 围炉' % circle['displayName'],
        'description': circle['description'],
      }
    else:
      rss_info = {
        'title': '请选择至少一种订阅类别',
        'description': '',
      }

    rss = base.data2rss(
      url,
      rss_info,
      edges,
      partial(edge2rssitem),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)


class MattersFeedHandler(base.BaseHandler):
  async def get(self):
    url = f'https://matters.news/'

    options = {
      'hottest': '热门',
      'newest': '最新',
      'icymi': '精华',
    }

    feed_type = self.get_argument('type', None)
    if feed_type not in ('hottest', 'newest', 'icymi'):
      feed_type = 'hottest'

    data = await matters_api.get_feed(feed_type)

    rss_info = {
      'title': 'Matters %s' % options[feed_type],
      'description': '',
    }

    rss = base.data2rss(
      url,
      rss_info,
      data['edges'],
      partial(article2rssitem),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)


class MattersUserHandler(base.BaseHandler):
  async def get(self, uname):
    url = f'https://matters.news/@{uname}'

    is_article = self.get_argument('article', '1')
    is_response = self.get_argument('response', '1')

    user = None
    edges = []
    if is_article == '1':
      data = await matters_api.get_articles_by_user(uname)
      user = data['user']
      edges.extend(data['user']['articles']['edges'])

    if is_response == '1':
      data = await matters_api.get_user_by_name(uname)
      user = data['user']

      data = await matters_api.get_comments_by_user(user['id'])
      edges.extend([edge1 for edge in data['commentedArticles']['edges']
                          for edge1 in edge['node']['comments']['edges']])

    if user:
      rss_info = {
        'title': '%s - Matters 用户' % user['displayName'],
        'description': user['info']['description'],
      }
    else:
      rss_info = {
        'title': '请选择至少一种订阅类别',
        'description': '',
      }

    rss = base.data2rss(
      url,
      rss_info,
      edges,
      partial(edge2rssitem),
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
      partial(article2rssitem),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)
