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

## 支持作者

你可以使用支付宝、微信支付或者 <a href="https://paypal.me/lilydjwg">PayPal</a> 向我付款来支持此项目/服务！

<small>付款请备注 rss 字样以让我知道你喜欢的是本项目/服务。</small>

![支付宝二维码](https://img.vim-cn.com/90/8882060ccc8cb65b543f6956b7d40336cb7adc.png)
![微信二维码](https://img.vim-cn.com/37/074ae3b290e5194b03d902a581ed006e493bcb.png)
