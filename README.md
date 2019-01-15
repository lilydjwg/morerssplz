各种转 RSS 服务。目前支持**知乎专栏**、**知乎动态**和 **v2ex 评论**。

网站的使用方法见 [https://rss.lilydjwg.me/](https://rss.lilydjwg.me/)。

程序依赖：

* Python >= 3.5
* Tornado >= 5 (旧版本可能也可以用）
* PyRSS2Gen
* lxml
* pycurl
* statsd (the Python library)

代理支持模块 `morerss.proxy` 是故意不提交的。如果需要，请自行实现。

程序源码许可证： GPLv3

## statsd 统计数据

* timing: morerss.zhihu.fetch
* timing: morerss.handler.Handler.Code
* count: morerss.zhihu.queue_full
* count: morerss.zhihu.cache_hit
* count: morerss.zhihu.cache_miss
