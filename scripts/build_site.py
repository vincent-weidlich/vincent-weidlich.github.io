#!/usr/bin/env python3
"""Build a dependency-free research website from an explicit publication selection."""
import argparse
import csv
import html
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'


def esc(value):
    return html.escape(str(value), quote=True)


def google_verification(site):
    """Accept a meta-tag token or Google's standard verification-file name."""
    value = os.environ.get('GOOGLE_SITE_VERIFICATION', '').strip() or site.get('google_site_verification', '').strip()
    if re.fullmatch(r'google[a-f0-9]{16,64}\.html', value):
        return '', value
    if value and not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Use the Google HTML tag content value or the google...html verification filename; do not paste a full tag or path.')
    return value, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.environ.get('SITE_URL', 'http://127.0.0.1:8766/'))
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    base = args.base_url.rstrip('/') + '/'
    parsed = urlparse(base)
    if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
        parser.error('Use a full website URL without query, fragment or credentials.')
    if args.production and (parsed.scheme != 'https' or parsed.hostname in ('localhost', '127.0.0.1') or parsed.hostname.endswith('.example')):
        parser.error('Production requires the real public HTTPS website address.')
    site = json.loads((ROOT / 'data/site.json').read_text())
    papers = json.loads((ROOT / 'data/publications.json').read_text())
    selected = site['selected_dois']
    if len(selected) != len(set(selected)) or len(papers) != len(selected) or set(p['doi'] for p in papers) != set(selected):
        raise ValueError('Publication records must match the explicit selected_dois list exactly.')
    slugs = [p['slug'] for p in papers]
    if len(set(slugs)) != len(slugs) or not all(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', s) for s in slugs):
        raise ValueError('Publication slugs must be unique, safe URL segments.')
    token, verification_file = google_verification(site)
    # This directory is generated only. Cleaning prevents old publications surviving a build.
    if OUT.is_symlink():
        raise ValueError('dist must not be a symbolic link')
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'assets').mkdir(parents=True)
    shutil.copyfile(ROOT / 'assets/style.css', OUT / 'assets/style.css')
    (OUT / '.nojekyll').write_text('')
    if verification_file:
        # Matches Google's downloaded single-line verification file exactly.
        # This ownership resource is deliberately absent from the sitemap.
        (OUT / verification_file).write_text('google-site-verification: ' + verification_file, encoding='utf-8')
    routes = []

    def url(path=''):
        return base + path.lstrip('/')

    def a(path, label, cls=''):
        return f'<a href="{esc(path)}"' + (f' class="{esc(cls)}"' if cls else '') + f'>{esc(label)}</a>'

    def page(path, title, description, body, lang='en', schema=None, translated=False, index=True, citations=None):
        canonical = url(path)
        head = f'<meta name="description" content="{esc(description)}"><link rel="canonical" href="{esc(canonical)}">'
        if not args.production or not index:
            head += '<meta name="robots" content="noindex,follow">'
        if token:
            head += f'<meta name="google-site-verification" content="{esc(token)}">'
        if translated:
            for code, route in [('en', ''), ('de', 'de/'), ('ru', 'ru/'), ('x-default', '')]:
                head += f'<link rel="alternate" hreflang="{code}" href="{esc(url(route))}">'
        if schema:
            head += '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c') + '</script>'
        if citations:
            head += ''.join(f'<meta name="{esc(name)}" content="{esc(value)}">' for name, value in citations)
        favicon = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"%3E%3Crect width="64" height="64" rx="12" fill="%23006974"/%3E%3Ctext x="32" y="44" text-anchor="middle" fill="white" font-family="Georgia" font-size="34"%3EV%3C/text%3E%3C/svg%3E'
        navigation = a(url(), 'Overview') + a(url('publications/'), 'Publications') + a(url('de/'), 'Deutsch') + a(url('ru/'), 'Русский')
        document = f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>{head}<link rel="icon" type="image/svg+xml" href='{favicon}'><link rel="stylesheet" href="{esc(url('assets/style.css'))}"></head>
<body><a class="skip" href="#main">Skip to content</a><div class="wrap"><header class="topbar">{a(url(), site['name'], 'brand')}<nav aria-label="Main navigation">{navigation}</nav></header>
<main id="main">{body}</main><footer class="footer"><span>{esc(site['name'])} · Selected research publications</span><span>{a(url('publications/'), 'Publication records')} · {a('https://github.com/vincent-weidlich', 'GitHub')}</span></footer></div></body></html>'''
        destination = OUT / path / 'index.html' if not path.endswith('.html') else OUT / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document, encoding='utf-8')
        if index:
            routes.append(canonical)

    def listing(items, summaries=False):
        rows = []
        for p in items:
            text = f'<p>{esc(p["summary"])}</p>' if summaries else ''
            rows.append(f'<li class="paper-row"><div class="year">{p["date"][:4]}</div><div><p class="meta">{esc(p["topic"])} · {esc(p["type"])}</p><h3>{a(url("publications/"+p["slug"]+"/"),p["title"])}</h3>{text}<div class="links">{a(url("publications/"+p["slug"]+"/"),"Abstract & details")}{a(url("assets/"+p["pdf_file"]),"Full paper (PDF)")}{a("https://doi.org/"+p["doi"],"DOI: "+p["doi"])}</div></div></li>')
        return '<ol class="paper-list">'+''.join(rows)+'</ol>'

    profiles = '<div class="links">' + ''.join(a(p['url'], p['label']) for p in site['profiles']) + '</div>'
    person = {'@type': 'Person', '@id': url('#person'), 'name': site['name'], 'url': base, 'sameAs': [p['url'] for p in site['profiles']]}
    home = '''<section class="hero"><div><p class="eyebrow">Research & publications</p><h1>Vincent Weidlich</h1><p class="intro">Published work on artificial intelligence in medicine, radiation oncology, thermal infrared imaging and decision theory.</p></div><aside class="topics" aria-label="Research topics"><p class="eyebrow">Areas of work</p><ul><li>AI in medicine</li><li>Image-guided radiotherapy</li><li>Thermal imaging</li><li>Decision theory</li></ul></aside></section>'''
    home += '<section class="section"><div class="section-head"><h2>Selected publications</h2>'+a(url('publications/'), 'View publication details')+'</div>'+listing(sorted(papers, key=lambda p:p['date'], reverse=True))+'</section>'
    home += '<section class="profile-strip"><h2>Research profiles</h2>'+profiles+'</section>'
    page('', site['name']+' | AI & Radiation Oncology Research', site['description'], home, schema={'@context':'https://schema.org','@type':'ProfilePage','mainEntity':person}, translated=True)

    downloads = '<div class="links">' + ''.join(a(url('selected-publications.'+ext), label, 'download') for ext, label in [('bib','BibTeX citations'),('ris','RIS citations'),('csv','CSV citations')]) + '</div>'
    collection = '<header class="page-head"><p class="eyebrow">Bibliography</p><h1>Selected publications</h1><p class="intro">Original abstracts, open-access full papers and publication records.</p>'+downloads+'</header><section class="section">'+listing(sorted(papers,key=lambda p:p['date'],reverse=True), True)+'</section>'
    page('publications/', 'Selected Publications | '+site['name'], 'Selected publications by Vincent Weidlich, with original DOI links, publication dates and summaries.', collection)
    for p in papers:
        if not re.fullmatch(r'cureus-[0-9]+\.pdf', p['pdf_file']):
            raise ValueError('Invalid PDF asset filename')
        pdf = ROOT / 'assets' / p['pdf_file']
        if not pdf.read_bytes().startswith(b'%PDF-') or hashlib.sha256(pdf.read_bytes()).hexdigest() != p['pdf_sha256']:
            raise ValueError('Original PDF missing or checksum mismatch: '+p['doi'])
        shutil.copyfile(pdf, OUT / 'assets' / p['pdf_file'])
        reference = f'{p["journal"]}. {p["date"][:4]};{p["volume"]}({p["issue"]}):{p["article_number"]}.'
        body = '<header class="page-head publication-head"><h1>'+esc(p['title'])+'</h1><p class="authors">'+esc('; '.join(p['authors']))+'</p><p class="meta">'+esc(reference)+' · '+esc(p['date'])+'</p></header>'
        body += '<article class="reading"><section aria-labelledby="abstract"><h2 id="abstract">Abstract</h2>'+''.join('<p>'+esc(paragraph)+'</p>' for paragraph in p['abstract'])+'</section>'
        body += '<div class="links">'+a(url('assets/'+p['pdf_file']),'Read full paper (PDF)','download')+a('https://doi.org/'+p['doi'],'Original publication · '+p['doi'])+'</div>'
        body += '<p class="attribution">Original abstract: '+a(p['abstract_license']['url'],p['abstract_license']['name'])+'. Unmodified published PDF: '+a(p['license']['url'],p['license']['name'])+'. '+esc(p['license']['copyright'])+' Source: '+a(p['full_text_url'],'PubMed Central, U.S. National Library of Medicine')+'; retrieved '+esc(p['source_checked'])+'. Check the original record for subsequent updates.</p>'
        body += '<h2>Research summary</h2><p>'+esc(p['summary'])+'</p><p class="scope">'+esc(p['scope'])+'</p><h2>Publication records</h2><div class="links">'+a(p['record_url'],'PubMed')+a(p['full_text_url'],'PubMed Central')+a(p['europe_pmc_url'],'Europe PMC')+a(p['scienceopen_url'],'ScienceOpen')+'</div><h2>Cite this paper</h2><div class="links">'+a(url('publications/'+p['slug']+'/citation.bib'),'BibTeX')+a(url('publications/'+p['slug']+'/citation.ris'),'RIS')+'</div>'+a(url('publications/'),'All selected publications','back')+'</article>'
        scholarly = {'@type':'ScholarlyArticle','@id':'https://doi.org/'+p['doi'],'name':p['title'],'identifier':p['doi'],'url':'https://doi.org/'+p['doi'],'datePublished':p['date'],'author':[{'@type':'Person','name':n} for n in p['authors']],'isPartOf':{'@type':'Periodical','name':p['journal']}}
        scholarly.update({'abstract':'\n\n'.join(p['abstract']),'license':p['license']['url'],'encoding':{'@type':'MediaObject','contentUrl':url('assets/'+p['pdf_file']),'encodingFormat':'application/pdf'}})
        citations = [('citation_title',p['title'])] + [('citation_author',n) for n in p['authors']] + [('citation_publication_date',p['date'].replace('-','/')),('citation_journal_title',p['journal']),('citation_volume',p['volume']),('citation_issue',p['issue']),('citation_firstpage',p['article_number']),('citation_doi',p['doi']),('citation_pmid',p['pmid']),('citation_pdf_url',url('assets/'+p['pdf_file']))]
        page('publications/'+p['slug']+'/',p['title']+' | '+site['name'],p['summary'],body,schema={'@context':'https://schema.org','@type':'WebPage','name':p['title'],'about':scholarly},citations=citations)

    # Preserve the original identifiers and dates when exporting existing publications.
    def bibtex(p):
        fields = {'title':'{'+p['title']+'}', 'author':' and '.join(n['family']+', '+n['given'] for n in p['author_names']), 'journal':p['journal'], 'year':p['date'][:4], 'volume':p['volume'], 'number':p['issue'], 'pages':p['article_number'], 'doi':p['doi'], 'url':'https://doi.org/'+p['doi']}
        return '@article{Weidlich'+p['date'][:4]+p['article_number']+',\n'+',\n'.join('  '+k+' = {'+str(v)+'}' for k,v in fields.items())+'\n}\n'

    def ris(p):
        fields = [('TY','JOUR'),('TI',p['title'])]+[('AU',n['family']+', '+n['given']) for n in p['author_names']]+[('JO',p['journal']),('PY',p['date'][:4]),('DA',p['date'].replace('-','/')),('VL',p['volume']),('IS',p['issue']),('SP',p['article_number']),('DO',p['doi']),('UR','https://doi.org/'+p['doi']),('ER','')]
        return '\n'.join(k+'  - '+v for k,v in fields)+'\n'

    for ext, render in [('bib',bibtex),('ris',ris)]:
        (OUT/('selected-publications.'+ext)).write_text('\n'.join(render(p) for p in papers),encoding='utf-8')
        for p in papers:
            (OUT/'publications'/p['slug']/('citation.'+ext)).write_text(render(p),encoding='utf-8')
    (OUT/'selected-dois.txt').write_text('\n'.join(p['doi'] for p in papers)+'\n',encoding='utf-8')

    translations = {
        'de': ('Forschung und Publikationen','Ausgewählte Publikationen','Die veröffentlichten Arbeiten von Vincent Weidlich befassen sich mit künstlicher Intelligenz in der Medizin, Strahlentherapie, thermischer Infrarotbildgebung und Entscheidungstheorie.','Die folgenden Titel stehen in ihrer ursprünglichen englischen Fassung. Die verlinkten Seiten enthalten englische Zusammenfassungen und Links zu den Originalartikeln.'),
        'ru': ('Исследования и публикации','Избранные публикации','Опубликованные работы Vincent Weidlich посвящены искусственному интеллекту в медицине, лучевой терапии, тепловой инфракрасной визуализации и теории принятия решений.','Названия работ приведены на языке оригинала — английском. Ссылки ведут на страницы с краткими описаниями на английском языке и ссылками на оригинальные статьи.')
    }
    for lang, (heading, selected_label, intro, note) in translations.items():
        body = f'<header class="page-head"><p class="eyebrow">{esc(heading)}</p><h1>Vincent Weidlich</h1><p class="intro">{esc(intro)}</p></header><section class="section"><h2>{esc(selected_label)}</h2><p>{esc(note)}</p>'+listing(sorted(papers,key=lambda p:p['date'],reverse=True))+'</section>'
        page(lang+'/',site['name']+' | '+heading,intro,body,lang=lang,translated=True)
    page('404.html', 'Page not found | '+site['name'], 'This page could not be found.', '<header class="page-head"><h1>Page not found</h1><p>'+a(url(),'Return to the research overview')+'</p></header>', index=False)

    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['title','authors','publication_date','journal','doi','record_url'])
    for p in papers:
        writer.writerow([p['title'],'; '.join(p['authors']),p['date'],p['journal'],p['doi'],p['record_url']])
    (OUT/'selected-publications.csv').write_text(stream.getvalue(),encoding='utf-8')
    ET.register_namespace('', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    sitemap = ET.Element('{http://www.sitemaps.org/schemas/sitemap/0.9}urlset')
    for route in routes:
        entry = ET.SubElement(sitemap, 'url')
        ET.SubElement(entry, 'loc').text = route
    ET.ElementTree(sitemap).write(OUT/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    (OUT/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+url('sitemap.xml')+'\n' if args.production else 'User-agent: *\nDisallow: /\n')
    key = site.get('indexnow_key', '')
    if key:
        if not re.fullmatch(r'[a-f0-9]{32}', key):
            raise ValueError('IndexNow key must be 32 lowercase hexadecimal characters.')
        (OUT/(key+'.txt')).write_text(key, encoding='utf-8')
    manifest = {}
    for route in routes:
        relative = route.removeprefix(base)
        manifest[relative] = hashlib.sha256((OUT/relative/'index.html').read_bytes()).hexdigest()
    for p in papers:
        manifest['assets/'+p['pdf_file']] = p['pdf_sha256']
    (OUT/'indexnow-manifest.json').write_text(json.dumps({'base_url':base,'pages':manifest},sort_keys=True,indent=2)+'\n')
    print(f'Built {len(routes)} indexable routes and a 404 page in {OUT}')
    print(f'Base URL: {base}; mode: '+('production' if args.production else 'local preview (noindex)'))


if __name__ == '__main__':
    main()
