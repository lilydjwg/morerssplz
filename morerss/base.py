import traceback
import http.client as httpclient

from tornado import web

class BaseHandler(web.RequestHandler):
  error_page = '''\
<!DOCTYPE html>
<meta charset="utf-8" />
<title>%(code)s %(message)s</title>
<style type="text/css">
  body { font-family: serif; }
</style>
<h1>%(code)s %(message)s</h1>
<p>%(err)s</p>
<hr/>
'''

  def initialize(self):
    self.set_header('Content-Type', 'application/rss+xml; charset=utf-8')
    self.set_header('Cache-Control', 'public, max-age=3600')

  def write_error(self, status_code, **kwargs):
    if self.settings.get("debug") and "exc_info" in kwargs:
      # in debug mode, try to send a traceback
      self.set_header('Content-Type', 'text/plain')
      for line in traceback.format_exception(*kwargs["exc_info"]):
        self.write(line)
      self.finish()
    else:
      err_exc = kwargs.get('exc_info', '  ')[1]
      if err_exc in (None, ' '):
        err_msg = ''
      else:
        if isinstance(err_exc, web.HTTPError):
          if err_exc.log_message is not None:
            err_msg = str(err_exc.log_message) + '.'
          else:
            err_msg = ''
        else:
          err_msg = str(err_exc) + '.'

      self.finish(self.error_page % {
        "code": status_code,
        "message": httpclient.responses[status_code],
        "err": err_msg,
      })
