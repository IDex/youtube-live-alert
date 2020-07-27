#!/usr/bin/env python
# coding: utf-8
import argparse
import concurrent.futures
import logging
import pathlib
import re
import subprocess
import time
import webbrowser

import yaml
from appdirs import user_config_dir
from munch import Munch
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options


def catch(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.info(e)

    return wrapper


class YoutubeLiveAlert:
    def __init__(self, config, player=None, verbose=False):
        config = Munch.fromDict(
            yaml.safe_load((pathlib.Path(config).read_text())))
        self.config = config.settings
        if player:
            self.config.player = player
        if self.config.verbose or verbose:
            logging.getLogger().setLevel(logging.INFO)
        self.channels = config.channels
        self.opt = Options()
        self.opt.headless = True
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.concurrent)
        self.seen = set()

    @catch
    def get_urls(self, u):
        """
        Alternative shortened: //text()[contains(.,'LIVE NOW')]/ancestor::*[@id='details']/descendant::a[@id='video-title']
        """
        d = Firefox(options=self.opt)
        d.get(u)
        title = d.title
        texts = ['LIVE NOW', 'PREMIERING NOW']
        for text in texts:
            try:
                link = d.find_element_by_xpath(
                    f"//text()[contains(.,'{text}')]/parent::*/parent::*/parent::*/parent::*/descendant::a[@id='video-title'][1]"
                ).get_attribute('href')
            except Exception as e:
                link = None
            if link: break
        source = d.page_source
        if link:
            logging.debug(
                f'Is the text inside link: {">LIVE NOW<" in d.page_source}, do we have a link: {link}'
            )
        result = Munch(title=title, link=link, source=source)
        d.quit()
        return result

    def check_new(self):
        tasks = Munch()
        new = set()
        for channel, url in self.channels.items():
            x = self.thread_pool.submit(self.get_urls, url)
            tasks[x] = channel
        results = dict()
        for res in concurrent.futures.as_completed(tasks):
            result = res.result()
            results[tasks[res]] = result
            try:
                if result.link:
                    new.add(result.link)
            except:
                pass
        new -= self.seen
        self.seen |= new
        return new

    def play(self, url, player):
        if self.config.separate_chat:
            video_id = re.findall(r'v=(.*)', url)[0]
            webbrowser.open_new(
                f'https://www.youtube.com/live_chat?is_popout=1&v={video_id}')
        if player == 'browser':
            webbrowser.open(url)
        else:
            if self.config.single_stream:
                subprocess.run([player, url])
            else:
                subprocess.Popen([player, url])

    def run(self):
        if self.config.only_new:
            self.check_new()
        while True:
            # logging.info(f'Going over channels')
            new = self.check_new()
            for url in new:
                logging.info(f'Found new links: {new}')
                for player in self.config.player.split():
                    self.play(url, player)
            time.sleep(self.config.wait)


def main():
    argparser = argparse.ArgumentParser(
        description='Detect and play streamers on youtube')
    argparser.add_argument('-c',
                           default=user_config_dir('youtubelivealert', 'ide') +
                           '/config.yml',
                           help='Config file location')
    argparser.add_argument('-p', help='Override default player')
    argparser.add_argument('-v', action='store_true', help='Verbose output')
    args = argparser.parse_args()
    config_path = pathlib.Path(args.c)
    if not config_path.exists():
        logging.warning(
            f'Config file does not exits. Attempting to create one at {config_path}'
        )
        config_path.parent.mkdir(exist_ok=True, parents=True)
        config_path.write_text("""\
settings:
  player: browser # How to play found streams
  concurrent: 5 # How many concurrent selenium instances to use for checking
  separate_chat: true # Open the chat in a separate window
  single_stream: true # Play only a single stream at a time, applies only to non-browser player
  wait: 60 # How long to wait between checks
  verbose: true # Show more output
  only_new: false # Ignore already running streams
channels:
  placeholder: https://www.youtube.com/channel/UC4R8DWoMoI7CAwX8_LjQHig
""")

    yla = YoutubeLiveAlert(config=args.c, player=args.p, verbose=args.v)
    yla.run()


if __name__ == '__main__':
    main()
