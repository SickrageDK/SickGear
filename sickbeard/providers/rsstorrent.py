# Author: Mr_Orange
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.


import os
import re
import urlparse

import sickbeard
import generic

from sickbeard import helpers
from sickbeard import encodingKludge as ek
from sickbeard import logger
from sickbeard import tvcache
from sickbeard import clients
from sickbeard.exceptions import ex

from lib import requests
from lib.requests import exceptions
from lib.bencode import bdecode


class TorrentRssProvider(generic.TorrentProvider):
    def __init__(self, name, url, cookies='', search_mode='eponly', search_fallback=False, enable_daily=False,
                 enable_backlog=False):
        generic.TorrentProvider.__init__(self, name)
        self.cache = TorrentRssCache(self)
        self.url = re.sub('\/$', '', url)
        self.url = url
        self.enabled = True
        self.ratio = None
        self.supportsBacklog = False

        self.search_mode = search_mode
        self.search_fallback = search_fallback
        self.enable_daily = enable_daily
        self.enable_backlog = enable_backlog
        self.cookies = cookies

    def configStr(self):
        return "%s|%s|%s|%d|%s|%d|%d|%d" % (self.name or '',
                                            self.url or '',
                                            self.cookies or '',
                                            self.enabled,
                                            self.search_mode or '',
                                            self.search_fallback,
                                            self.enable_daily,
                                            self.enable_backlog)

    def imageName(self):
        if ek.ek(os.path.isfile,
                 ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', sickbeard.GUI_NAME, 'images', 'providers',
                       self.getID() + '.png')):
            return self.getID() + '.png'
        return 'torrentrss.png'

    def isEnabled(self):
        return self.enabled

    def _get_title_and_url(self, item):

        title, url = None, None

        title = item.title

        if title:
            title = u'' + title
            title = title.replace(' ', '.')

        attempt_list = [lambda: item.torrent_magneturi,

                        lambda: item.enclosures[0].href,

                        lambda: item.link]

        for cur_attempt in attempt_list:
            try:
                url = cur_attempt()
            except:
                continue

            if title and url:
                return (title, url)

        return (title, url)

    def validateRSS(self):

        try:
            if self.cookies:
                cookie_validator = re.compile("^(\w+=\w+)(;\w+=\w+)*$")
                if not cookie_validator.match(self.cookies):
                    return (False, 'Cookie is not correctly formatted: ' + self.cookies)

            items = self.cache._getRSSData()

            if not len(items) > 0:
                return (False, 'No items found in the RSS feed ' + self.url)

            (title, url) = self._get_title_and_url(items[0])

            if not title:
                return (False, 'Unable to get title from first item')

            if not url:
                return (False, 'Unable to get torrent url from first item')

            if url.startswith('magnet:') and re.search('urn:btih:([\w]{32,40})', url):
                return (True, 'RSS feed Parsed correctly')
            else:
                if self.cookies:
                    requests.utils.add_dict_to_cookiejar(self.session.cookies,
                                                         dict(x.rsplit('=', 1) for x in (self.cookies.split(';'))))
                torrent_file = self.getURL(url)
                try:
                    bdecode(torrent_file)
                except Exception, e:
                    self.dumpHTML(torrent_file)
                    return (False, 'Torrent link is not a valid torrent file: ' + ex(e))

            return (True, 'RSS feed Parsed correctly')

        except Exception, e:
            return (False, 'Error when trying to load RSS: ' + ex(e))

    def dumpHTML(self, data):

        dumpName = ek.ek(os.path.join, sickbeard.CACHE_DIR, 'custom_torrent.html')

        try:
            fileOut = open(dumpName, 'wb')
            fileOut.write(data)
            fileOut.close()
            helpers.chmodAsParent(dumpName)
        except IOError, e:
            logger.log("Unable to save the file: " + ex(e), logger.ERROR)
            return False
        logger.log(u"Saved custom_torrent html dump " + dumpName + " ", logger.MESSAGE)
        return True

    def seedRatio(self):
        return self.ratio


class TorrentRssCache(tvcache.TVCache):
    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)
        self.minTime = 15

    def _getRSSData(self):
        logger.log(u"TorrentRssCache cache update URL: " + self.provider.url, logger.DEBUG)

        request_headers = None
        if self.provider.cookies:
            request_headers = {'Cookie': self.provider.cookies}

        data = self.getRSSFeed(self.provider.url, request_headers=request_headers)

        if data and 'entries' in data:
            return data.entries
        else:
            return []
