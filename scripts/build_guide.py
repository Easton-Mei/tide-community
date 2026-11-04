#!/usr/bin/env python3
"""Derive Markdown/export from the user-approved concise HTML; never expand it."""
import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


class Markdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.pre = False
        self.footer = False
        self.links = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.active = True
        if not self.active:
            return
        if tag == 'footer':
            self.footer = True
        if self.footer:
            return
        attrs = dict(attrs)
        if tag in ('h1', 'h2', 'h3'):
            self.parts.append('\n\n' + '#' * int(tag[1]) + ' ')
        elif tag == 'p':
            self.parts.append('\n\n')
        elif tag == 'li':
            self.parts.append('\n- ')
        elif tag == 'pre':
            self.pre = True
            self.parts.append('\n\n```text\n')
        elif tag == 'strong':
            self.parts.append('**')
        elif tag == 'code' and not self.pre:
            self.parts.append('`')
        elif tag == 'a':
            self.links.append(attrs.get('href', ''))
            self.parts.append('[')

    def handle_endtag(self, tag):
        if tag == 'main':
            self.active = False
        if not self.active or self.footer:
            return
        if tag == 'pre':
            self.pre = False
            self.parts.append('\n```\n\n')
        elif tag in ('p', 'h1', 'h2', 'h3', 'ul', 'ol'):
            self.parts.append('\n\n')
        elif tag == 'strong':
            self.parts.append('**')
        elif tag == 'code' and not self.pre:
            self.parts.append('`')
        elif tag == 'a':
            self.parts.append('](' + self.links.pop() + ')')

    def handle_data(self, text):
        if self.active and not self.footer:
            self.parts.append(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, help='Optional standalone HTML destination')
    args = parser.parse_args()
    html = (ROOT / 'docs/开始阅读.html').read_text(encoding='utf-8')
    markdown = Markdown()
    markdown.feed(html)
    text = re.sub(r'\n{3,}', '\n\n', ''.join(markdown.parts)).strip() + '\n'
    (ROOT / 'docs/新手教程.md').write_text(text, encoding='utf-8')
    if args.output:
        css = (ROOT / 'docs/guide.css').read_text(encoding='utf-8')
        args.output.write_text(html.replace('<link rel="stylesheet" href="guide.css">', '<style>' + css + '</style>'), encoding='utf-8')


if __name__ == '__main__':
    main()
