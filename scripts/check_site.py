#!/usr/bin/env python3
"""Check the built pages before publishing; Python standard library only."""
import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.canonicals, self.robots, self.verification, self.jsonld = [], [], [], [], []
        self.h1 = 0
        self.active_json = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('a', 'link') and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag in ('img', 'script') and attrs.get('src'):
            self.links.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name') == 'robots':
            self.robots.append(attrs.get('content', ''))
        if tag == 'meta' and attrs.get('name') == 'google-site-verification':
            self.verification.append(attrs.get('content', ''))
        if tag == 'h1':
            self.h1 += 1
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.active_json = ''

    def handle_data(self, data):
        if self.active_json is not None:
            self.active_json += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.active_json is not None:
            self.jsonld.append(json.loads(self.active_json))
            self.active_json = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.environ.get('SITE_URL', 'http://127.0.0.1:8766/'))
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    base = args.base_url.rstrip('/') + '/'
    site = json.loads((ROOT/'data/site.json').read_text())
    papers = json.loads((ROOT/'data/publications.json').read_text())
    selected = set(site['selected_dois'])
    token = os.environ.get('GOOGLE_SITE_VERIFICATION', '').strip() or site.get('google_site_verification', '')
    out = ROOT/'dist'
    expected_paths = {'index.html', 'publications/index.html', 'de/index.html', 'ru/index.html', '404.html'} | {'publications/'+p['slug']+'/index.html' for p in papers}
    actual_paths = {str(p.relative_to(out)) for p in out.rglob('*.html')}
    assert actual_paths == expected_paths, 'Unexpected or missing HTML pages'
    expected_urls = set()
    scholarly_dois = set()
    for relative in actual_paths:
        route = '' if relative == 'index.html' else relative.removesuffix('index.html')
        expected_url = base + route
        doc = Document((out/relative).read_text())
        assert doc.h1 == 1, f'Expected one main heading: {relative}'
        assert doc.canonicals == [expected_url], f'Canonical mismatch: {relative}'
        assert doc.verification == ([token] if token else []), 'Google verification tag mismatch'
        if relative != '404.html':
            expected_urls.add(expected_url)
            assert ('noindex' in ','.join(doc.robots)) != args.production, f'Incorrect indexing mode: {relative}'
        for schema in doc.jsonld:
            article = schema.get('about', {})
            if article.get('@type') == 'ScholarlyArticle':
                assert article['identifier'] in selected, 'Unselected publication in structured data'
                scholarly_dois.add(article['identifier'])
        for link in doc.links:
            resolved = urljoin(expected_url, link)
            parsed = urlparse(resolved)
            if parsed.netloc == urlparse(base).netloc and parsed.scheme in ('http','https'):
                assert resolved.split('#')[0].startswith(base), f'Link escapes website base path: {link}'
                local = unquote(parsed.path.removeprefix(urlparse(base).path))
                target = out/local
                if target.is_dir():
                    target = target/'index.html'
                assert target.is_file(), f'Broken local link: {link} in {relative}'
    assert scholarly_dois == selected, 'Missing selected publication detail metadata'
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = [n.text for n in ET.parse(out/'sitemap.xml').findall('.//s:loc', ns)]
    assert len(urls) == len(set(urls)) and set(urls) == expected_urls, 'Sitemap route mismatch'
    import csv
    with (out/'selected-publications.csv').open(newline='') as handle:
        assert {p['doi'] for p in csv.DictReader(handle)} == selected, 'CSV selection mismatch'
    if args.production:
        assert 'Disallow: /' not in (out/'robots.txt').read_text(), 'Production robots blocks crawling'
        assert base+'sitemap.xml' in (out/'robots.txt').read_text()
    assert not any(p.suffix in ('.py', '.md') for p in out.rglob('*')), 'Source files in deployment'
    print(f'PASS: {len(actual_paths)} pages; internal links; canonical URLs; sitemap; {len(selected)} selected records; Google verification; indexing mode.')


if __name__ == '__main__':
    main()
