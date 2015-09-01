# -*- coding: utf-8 -*-

#
# Copyright (c) 2011-2015 Genestack Limited
# All Rights Reserved
# THIS IS UNPUBLISHED PROPRIETARY SOURCE CODE OF GENESTACK LIMITED
# The copyright notice above does not evidence any
# actual or intended publication of such source code.
#

import os
import sys
import urllib
import urllib2
import cookielib
import json
import requests
from Exceptions import GenestackServerException, GenestackException
from utils import isatty
from chunked_upload import upload_by_chunks
from version import __version__
from distutils.version import StrictVersion


class AuthenticationErrorHandler(urllib2.HTTPErrorProcessor):
    def http_error_401(self, req, fp, code, msg, headers):
        raise GenestackException('Authentication failure')


class _NoRedirect(urllib2.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        #print 'Redirect: %s %s %s -> %s' % (code, msg, req.get_full_url(), newurl)
        return


class _NoRedirectError(urllib2.HTTPErrorProcessor):
    def http_error_307(self, req, fp, code, msg, headers):
        return fp
    http_error_301 = http_error_302 = http_error_303 = http_error_307


class Connection:
    """
    Connection to specified url. Server url is not same as host. If include protocol host and path: ``https://platform.genestack.org/endpoint``

    Connection is not logged by default. To access applications methods you need to :attr:`login`.
    """

    def __init__(self, server_url):
        self.server_url = server_url
        cj = cookielib.CookieJar()
        self.__cookies_jar = cj
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj), AuthenticationErrorHandler)
        self.opener.addheaders.append(('gs-extendSession', 'true'))
        self._no_redirect_opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj), _NoRedirect, _NoRedirectError, AuthenticationErrorHandler)

    def __del__(self):
        try:
            self.logout()
        except Exception:
            # fail silently
            pass

    def whoami(self):
        """
        Return user email.

        :return: email
        :rtype: str
        """
        return self.application('genestack/signin').invoke('whoami')

    def login(self, email, password):
        """
        Login connection with given credentials. Raises exception if login failed.

        :param email: login at server
        :type email: str
        :param password: password
        :type password: str
        :rtype: None
        :raises: GenestackServerException: if login failed
        """
        logged = self.application('genestack/signin').invoke('authenticate', email, password)
        if not logged['authenticated']:
            raise GenestackException("Fail to login %s" % email)
        version_msg = self.check_version(__version__)
        if version_msg:
            print 'Warning: %s' % version_msg

    def check_version(self, version):
        """
        Check version required by server.
        Server output contain latest and minimum compatible versions.
        Return message about version compatibility.
        If version is not compatible exception raised.

        :param version: version in format suitable for distutils.version.StrictVersion
        :return: user friendly message.
        """
        version_map = self.application('genestack/clientVersion').invoke('getCurrentVersion')
        LATEST = 'latest'
        COMPATIBLE = 'compatible'

        latest_version = StrictVersion(version_map[LATEST])
        my_verison = StrictVersion(version)

        if latest_version < my_verison:
            return 'You use version from future'

        if latest_version == my_verison:
            return ''

        compatible = StrictVersion(version_map[COMPATIBLE])
        if my_verison >= compatible:
            return 'Newer version "%s" available, please update.' % latest_version
        else:
            raise GenestackException('Your version "%s" is too old, please update to %s' % (my_verison, latest_version))

    def logout(self):
        """
        Logout from server.

        :rtype: None
        """
        self.application('genestack/signin').invoke('signOut')

    def open(self, path, data=None, follow=True):
        """
        Sends data to url. Url is concatenated server url and path.

        :param path: part of url that added to self.server_url
        :param data: dict of parameters or file-like object or string
        :param follow: flag to follow redirect
        :return: response
        :rtype: urllib.addinfourl
        """
        if data is None:
            data = ''
        elif isinstance(data, dict):
            data = urllib.urlencode(data)
        try:
            if follow:
                return self.opener.open(self.server_url + path, data)
            else:
                return self._no_redirect_opener.open(self.server_url + path, data)
        except urllib2.URLError, e:
            raise urllib2.URLError('Fail to connect %s%s %s' % (self.server_url,
                                                                path,
                                                                str(e).replace('urlopen error', '').strip('<\ >')))

    def application(self, application_id):
        """
        Return documentation with specified id.

        :param application_id: application_id.
        :type application_id: str
        :return: application class
        :rtype: Application
        """
        return Application(self, application_id)

    def __repr__(self):
        return 'Connection("%s")' % self.server_url

    def get_request(self, path, params=None, follow=True):
        r = requests.get(self.server_url + path, params=params, allow_redirects=follow, cookies=self.__cookies_jar)
        return r

    def post_multipart(self, path, data=None, files=None, follow=True):
        r = requests.post(self.server_url + path, data=data, files=files, allow_redirects=follow, cookies=self.__cookies_jar)
        return r


class Application:
    """
    Create new application instance for given connection. Connection must be logged in to call methods.

    application_id can be specified as init argument or in APPLICATION_ID class variable in case of using inheritance.
    """

    APPLICATION_ID = None

    def __init__(self, connection, application_id=None):
        if application_id and self.APPLICATION_ID:
            raise GenestackException("Application ID specified both as argument and as class variable")
        self.application_id = application_id or self.APPLICATION_ID
        if not self.application_id:
            raise GenestackException('Application ID was not specified')

        self.connection = connection

        # validation of application ID
        if len(self.application_id.split('/')) != 2:
            raise GenestackException('Invalid application ID, expect "{vendor}/{application}" got: %s' % self.application_id)

    def __invoke(self, path, to_post):
        f = self.connection.open(path, to_post)
        response = json.load(f)
        if isinstance(response, dict) and 'error' in response:
            raise GenestackServerException(
                response['error'], path, to_post,
                stack_trace=response.get('errorStackTrace')
            )
        return response

    def invoke(self, method, *params):
        """
        Invoke application method.

        :param method: name of method
        :type method: str
        :param params: arguments that will be passed to java method. Arguments must be json serializable.
        :return: json deserialized response.
        """

        to_post = {'method': method}
        if params:
            to_post['parameters'] = json.dumps(params)

        path = '/application/invoke/%s' % self.application_id

        return self.__invoke(path, to_post)

    def upload_chunked_file(self, file_path):
        return upload_by_chunks(self, file_path)

    def upload_file(self, file_path, token):
        """
        Upload file to server storage. Require special token that can be generated by application.

        :param file_path: path to existing file.
        :type file_path: str
        :param token: upload token
        :type file_path: str
        :rtype: None
        """
        if isatty():
            progress = TTYProgress()
        else:
            progress = DottedProgress(40)

        file_to_upload = FileWithCallback(file_path, 'rb', progress)
        filename = os.path.basename(file_path)
        path = '/application/upload/%s/%s/%s' % (
            self.application_id, token, urllib.quote(filename)
        )
        return self.__invoke(path, file_to_upload)


class FileWithCallback(file):
    def __init__(self, path, mode, callback):
        file.__init__(self, path, mode)
        self.seek(0, os.SEEK_END)
        self.__total = self.tell()
        self.seek(0)
        self.__callback = callback

    def __len__(self):
        return self.__total

    def read(self, size=None):
        data = file.read(self, size)
        self.__callback(os.path.basename(self.name), len(data), self.__total)
        return data


class TTYProgress(object):
    def __init__(self):
        self._seen = 0.0

    def __call__(self, name, size, total):
        if size > 0 and total > 0:
            self._seen += size
            pct = self._seen * 100.0 / total
            sys.stderr.write('\rUploading %s - %.2f%%' % (name, pct))
            if int(pct) >= 100:
                sys.stderr.write('\n')
            sys.stderr.flush()


class DottedProgress(object):
    def __init__(self, full_length):
        self.__full_length = full_length
        self.__dots = 0
        self.__seen = 0.0

    def __call__(self, name, size, total):
        if size > 0 and total > 0:
            if self.__seen == 0:
                sys.stderr.write('Uploading %s: ' % name)
            self.__seen += size
            dots = int(self.__seen * self.__full_length / total)
            while dots > self.__dots and self.__dots < self.__full_length:
                self.__dots += 1
                sys.stderr.write('.')
            if self.__dots == self.__full_length:
                sys.stderr.write('\n')
            sys.stderr.flush()