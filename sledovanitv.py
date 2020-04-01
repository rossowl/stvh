#!/usr/bin/env python3

import argparse
import requests
import logging
import os.path
import json
import pytz

from datetime import datetime
from datetime import timedelta
from lxml import etree
from functools import wraps

DEVICE = '*** YOUR DEVICE ID HERE ***'
PASSWORD = '*** YOUR DEVICE PASSWORD HERE ***'
PIN = '*** YOUR PARENT PIN HERE ***' # ex. '1234' or None for no-pin channels only
ENABLE_CACHE = True
CACHE_DIR = '/home/hts/.cache/'
TOKEN_CACHE_MIN = 60
EPG_CACHE_MIN = 60
PLAYLIST_CACHE_MIN = 60
QUALITY_SD = 20
QUALITY_HD = 40
QUALITY = QUALITY_HD
CAPABILITIES = 'h265,adaptive'
EPG_DURATION = 1439
TYPES = ('tv',)  # or ('radio', ) or ('tv', 'radio', )

# logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)


def cache(pathname, cache_min, *, enable_cache):

    def decorator(func):

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if enable_cache and os.path.exists(pathname):
                if datetime.now() - timedelta(minutes=cache_min) < datetime.fromtimestamp(os.path.getmtime(pathname)):
                    with open(pathname, 'r') as f:
                        logging.info(f'{f} from cache')

                        return f.read()

            result = func(self, *args, **kwargs)

            with open(pathname, 'w') as f:
                f.write(result)

            return result

        return wrapper

    return decorator


def string_generator(func_or_str=None, string=''):

    def decorator(f):

        @wraps(f)
        def wrapper(self, *args, **kwargs):
            if func_or_str and not callable(func_or_str):
                return func_or_str.join(list(f(self, *args, **kwargs)))

            return string.join(list(f(self, *args, **kwargs)))

        return wrapper

    if callable(func_or_str):
        return decorator(func_or_str)

    return decorator


class SledovaniError(Exception):
    ...


class Sledovani:

    def __init__(self, *, token, epg, playlist):
        self.token = token
        self.epg = epg
        self.playlist = playlist

    def parse_command(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('command', type=str)

        args, rem_args = parser.parse_known_args()

        if args.command == 'epg':
            print(self.epg)

        if args.command == 'playlist':
            print(self.playlist)

        if args.command == 'player':
            parser.add_argument('stream', type=str)

            args = parser.parse_args()

            os.system(f'ffmpeg -re -fflags +genpts -hide_banner -loglevel panic -i "{self.playlist.get_url(args.stream)}" -f mpegts -vcodec copy -acodec copy pipe:1')


class SledovaniToken:

    def __init__(self, *, device, password, pin=None):
        self.device = device
        self.password = password
        self.pin = pin

    @cache(os.path.join(CACHE_DIR, 'sledovanitv_token'), TOKEN_CACHE_MIN, enable_cache=ENABLE_CACHE)
    def get_token(self):
        logging.info('token from web')

        r = requests.get(f'http://sledovanitv.cz/api/device-login?deviceId={self.device}&password={self.password}&unit=default')

        data = r.json()

        if (data['status'] != 1):
            raise SledovaniError(r.text)

        token = data['PHPSESSID']

        if self.pin:
            logging.info('pin request')

            requests.get(f'https://sledovanitv.cz/api/pin-unlock?pin=${self.pin}&whitelogo=1&PHPSESSID=${token}')

        return token


class SledovaniEPG:

    def __init__(self, *, token, duration):
        self.token = token
        self.duration = duration

    def __str__(self):
        return str(self.xmltv())

    @cache(os.path.join(CACHE_DIR, 'sledovanitv-epg.json'), EPG_CACHE_MIN, enable_cache=ENABLE_CACHE)
    def epg(self):
        logging.info('epg from web')

        r = requests.get(f'https://sledovanitv.cz/api/epg?PHPSESSID={self.token.get_token()}&detail=1&duration={self.duration}')

        data = r.json()

        if (data['status'] != 1):
            raise SledovaniError(r.text)

        return r.text

    @cache(os.path.join(CACHE_DIR, 'sledovanitv-epg.xml'), EPG_CACHE_MIN, enable_cache=ENABLE_CACHE)
    def xmltv(self):
        logging.info('xmltv create')

        data = json.loads(self.epg())

        root = etree.Element('tv')
        root.set('generator-info-name', 'sledovanitv.py')

        for key, items in data['channels'].items():
            channel = etree.SubElement(root, 'channel', id=key)

            name = etree.SubElement(channel, 'display-name', lang='cs')
            name.text = key

        timezone = pytz.timezone('Europe/Prague')

        for key, items in data['channels'].items():
            for item in items:
                start = timezone.localize(datetime.strptime(item['startTime'], '%Y-%m-%d %H:%M'))
                stop = timezone.localize(datetime.strptime(item['endTime'], '%Y-%m-%d %H:%M'))

                programme = etree.SubElement(root, 'programme', channel=key, start=start.strftime('%Y%m%d%H%M%S %z'), stop=stop.strftime('%Y%m%d%H%M%S %z'))

                title = etree.SubElement(programme, 'title', lang='cs')
                title.text = item['title']

                desc = etree.SubElement(programme, 'desc', lang='cs')
                desc.text = item['description']

        return etree.tostring(root, encoding='utf-8', pretty_print=False).decode('utf-8')


class SledovaniPlaylist:

    def __init__(self, *, token, pin, quality, capabilities):
        self.token = token
        self.quality = quality
        self.capabilities = capabilities
        self.pin = pin

    def __str__(self):
        return str(self.m3u())

    @cache(os.path.join(CACHE_DIR, 'sledovanitv-playlist.json'), PLAYLIST_CACHE_MIN, enable_cache=ENABLE_CACHE)
    def playlist(self):
        r = requests.get(f'https://sledovanitv.cz/api/playlist?PHPSESSID={self.token.get_token()}&quality={self.quality}&capabilities={self.capabilities}')

        data = r.json()

        if (data['status'] != 1):
            raise SledovaniError(r.text)

        return r.text

    @cache(os.path.join(CACHE_DIR, 'sledovanitv-playlist.m3u'), PLAYLIST_CACHE_MIN, enable_cache=ENABLE_CACHE)
    @string_generator('\n')
    def m3u(self):
        logging.info('m3u create')

        data = json.loads(self.playlist())

        yield '#EXTM3U'

        for item in data['channels']:
            if item["type"] in TYPES and (item["locked"] == 'none' or (item["locked"] == 'pin' and self.pin)):
                yield f'#EXTINF:-1 tvg-id="{item["id"]}" epg-id="{item["id"]}" tvg-name="{item["name"]}" tvg-logo="{item["logoUrl"]}",{item["name"]}'
                yield f'pipe:///home/hts/bin/sledovanitv.py player {item["id"]}'

    def get_url(self, stream):
        data = json.loads(self.playlist())

        for item in data['channels']:
            if item['id'] == stream:
                return item['url']


if __name__ == '__main__':
    token = SledovaniToken(
        device=DEVICE,
        password=PASSWORD,
        pin=PIN
    )

    epg = SledovaniEPG(
        token=token,
        duration=EPG_DURATION
    )

    playlist = SledovaniPlaylist(
        token=token,
        quality=QUALITY,
        capabilities=CAPABILITIES,
        pin=PIN
    )

    Sledovani(token=token, epg=epg, playlist=playlist).parse_command()
