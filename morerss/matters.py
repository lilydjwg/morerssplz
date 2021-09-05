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
                ...ArticleFeed
              }
            }
          }
        }
      }

      %s
    """ % (uid, self.article_fragment)

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
                        ...FeedCommentPublic
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }

      fragment FeedCommentPublic on Comment {
        ...CommentDigest

        replyTo { ...CommentDigest }

        parentComment { id }

        node { ...ArticleFeed }
      }

      fragment CommentDigest on Comment {
        id
        content
        createdAt
        author {
          id
          userName
          displayName
        }
      }

      %s
    """ % (uid, uid, self.article_fragment)

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


def article2rss(edge):
  article = edge['node']

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


def comment2rss(edge):
  comment = edge['node']
  article = comment['node']

  author_url = f'https://matters.news/@{comment["author"]["userName"]}'
  article_url = f'https://matters.news/@{article["author"]["userName"]}/{article["slug"]}-{article["mediaHash"]}'
  if comment['parentComment']:
    comment_url = f'{article_url}#{comment["parentComment"]["id"]}-{comment["id"]}'
  else:
    comment_url = f'{article_url}#i{comment["id"]}'

  content = """
    <div><a href='%s'>%s</a> 在 <a href='%s'>《%s》</a> 下的评论</div>
    <div>%s</div>
    <p>%s</p>
  """ % (author_url, comment['author']['displayName'],
         article_url, article['title'],
         comment['content'], comment['createdAt'])

  if comment['replyTo']:
    author_url = f'https://matters.news/@{comment["replyTo"]["author"]["userName"]}'
    reply_to_content = """
      <blockquote>
        <p>回复： <a href='%s'>%s</a></p>
        <div>%s</div>
        <p>%s</p>
      </blockquote>
    """ % (author_url, comment['replyTo']['author']['displayName'],
           comment['replyTo']['content'], comment['replyTo']['createdAt'])
    content += reply_to_content

  import re
  item = PyRSS2Gen.RSSItem(
    title=re.split(',|，|\.|。|;|；|!|！|\?|？|~', comment['content'])[0].replace('<p>', ''),
    link=comment_url,
    guid=comment_url,
    description=content,
    author=comment['author']['displayName'],
    pubDate=comment['createdAt'],
  )

  return item


class MattersCircleArticleHandler(base.BaseHandler):
  async def get(self, cname):
    url = f'https://matters.news/~{cname}'

    data = await matters_api.get_articles_by_circle(cname)
    circle = data['circle']

    rss_info = {
      'title': '%s - 作品 - Matters 围炉' % circle['displayName'],
      'description': circle['description'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      circle['articles']['edges'],
      partial(article2rss),
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
      partial(article2rss),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)


class MattersUserResponseHandler(base.BaseHandler):
  async def get(self, uname):
    url = f'https://matters.news/@{uname}/comments/'

    data = await matters_api.get_user_by_name(uname)
    user = data['user']

    data = await matters_api.get_comments_by_user(user['id'])

    rss_info = {
      'title': '%s - Matters 用户回复' % user['displayName'],
      'description': user['info']['description'],
    }

    rss = base.data2rss(
      url,
      rss_info,
      [edge1 for edge in data['commentedArticles']['edges']
             for edge1 in edge['node']['comments']['edges']],
      partial(comment2rss),
    )

    xml = rss.to_xml(encoding='utf-8')
    self.finish(xml)


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
