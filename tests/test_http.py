import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from app import core, server


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patch=patch.object(core,'HOME',Path(self.tmp.name));self.patch.start()
        core.initialize()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.http.server_port)

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join()
        self.patch.stop();self.tmp.cleanup()

    def request(self,path,body=None,headers=None):
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
        return urllib.request.urlopen(request)

    def test_csrf_host_and_cross_origin_guards(self):
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.request('/api/settings',{})
        self.assertEqual(result.exception.code,403)
        for headers in ({'Host':'evil.example'}, {'Sec-Fetch-Site':'cross-site'}):
            with self.assertRaises(urllib.error.HTTPError):
                self.request('/api/state',headers=headers)
        with self.request('/api/session') as response:
            token=json.load(response)['token']
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/settings',{}, {'X-Tide-Token':token,'Origin':'https://evil.example'})
        with self.request('/api/settings',{'quotes':False},{'X-Tide-Token':token}) as response:
            self.assertTrue(json.load(response)['saved'])

    def test_secrets_not_in_state_and_path_traversal_blocked(self):
        core.save_secrets({'api_key':'private-key-test'})
        with self.request('/api/state') as response:
            self.assertNotIn(b'private-key-test',response.read())
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/report/../../data/secrets')

    def test_html_self_contained_security_headers(self):
        with self.request('/') as response:
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            self.assertIn('潮汐',response.read().decode())


if __name__=='__main__':unittest.main()
