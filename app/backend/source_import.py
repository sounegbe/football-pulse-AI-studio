"""Bounded, public-only HTTPS source import. Imported text is untrusted evidence."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

# Exact hostnames only; no user-configurable wildcard or redirect destination.
IMPORT_HOSTS = frozenset(host for domain in ('premierleague.com', 'uefa.com', 'fifa.com', 'arsenal.com', 'mancity.com', 'thefa.com', 'bbc.com', 'bbc.co.uk') for host in (domain, 'www.' + domain))
MAX_DOWNLOAD_BYTES = 1024 * 1024
MAX_SOURCE_CHARS = 100000

class SourceImportError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def canonical_url(value):
    if not value or len(value) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in value) or '\\' in value:
        raise ValueError('Use a plain public HTTPS URL without spaces or control characters')
    if any(ord(c) < 32 for c in unquote(value)):
        raise ValueError('Encoded control characters are not allowed')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError('Use HTTPS on port 443 without credentials or fragments')
    host = parsed.hostname.lower()
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host) or '.' not in host or '..' in host or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('A public domain name is required')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('IP literal URLs are not allowed')
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=50) if not key.lower().startswith('utm_') and key.lower() not in ('fbclid','gclid')]
    path = parsed.path or '/'
    return urlunsplit(('https', host, path, urlencode(sorted(query)), ''))


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.title_parts = []
        self.in_title = False
        self.article_depth = 0
        self.article_parts = []
        self.published_at = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script','style','noscript','nav','footer','header','svg'):
            self.hidden += 1
        if tag == 'title':
            self.in_title = True
        if tag == 'article':
            self.article_depth += 1
        if tag == 'meta' and (attrs.get('property') == 'article:published_time' or attrs.get('name') == 'datePublished'):
            self.published_at = attrs.get('content')

    def handle_endtag(self, tag):
        if tag in ('script','style','noscript','nav','footer','header','svg'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'title':
            self.in_title = False
        if tag == 'article':
            self.article_depth = max(0, self.article_depth - 1)

    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title_parts.append(data)
        elif data.strip():
            self.parts.append(data)
            if self.article_depth:
                self.article_parts.append(data)

    def result(self):
        text = ' '.join(' '.join(self.article_parts or self.parts).split())
        if not text or len(text) > MAX_SOURCE_CHARS:
            raise SourceImportError('source_text_invalid', 'The page contains no usable text or exceeds the text limit.')
        published = None
        if self.published_at:
            try:
                date = datetime.fromisoformat(self.published_at.replace('Z', '+00:00'))
                if date.tzinfo and date <= datetime.now(timezone.utc):
                    published = date.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        return {'text': text, 'title': ' '.join(' '.join(self.title_parts).split())[:200] or 'Imported source', 'published_at': published}


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, 443, timeout=8, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def public_address(host):
    try:
        addresses = sorted({record[4][0] for record in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise SourceImportError('source_dns_failed', 'The source domain could not be resolved.') from exc
    if not addresses:
        raise SourceImportError('source_dns_failed', 'The source domain has no address.')
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip, 'ipv4_mapped', None) or getattr(ip, 'sixtofour', None) or getattr(ip, 'teredo', None):
            raise SourceImportError('source_address_denied', 'The source domain resolved to a prohibited address.')
    return addresses[0]


def fetch_source(url):
    canonical = canonical_url(url)
    parsed = urlsplit(canonical)
    if parsed.hostname not in IMPORT_HOSTS:
        raise SourceImportError('source_host_denied', 'URL import is limited to approved football publishers. Paste source text for other public publishers.')
    address = public_address(parsed.hostname)
    connection = PinnedHTTPSConnection(parsed.hostname, address)
    started = time.monotonic()
    try:
        path = parsed.path + ('?' + parsed.query if parsed.query else '')
        connection.request('GET', path, headers={'User-Agent':'FootballPulseStudio/0.1 source-review', 'Accept':'text/html,text/plain', 'Accept-Encoding':'identity'})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise SourceImportError('source_redirect_denied', 'The source redirected. Submit its final approved HTTPS URL explicitly.')
        if response.status != 200:
            raise SourceImportError('source_http_failed', 'The publisher did not return an available article.')
        mime = response.getheader('Content-Type', '').split(';')[0].lower()
        if mime not in ('text/html','text/plain') or response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise SourceImportError('source_format_denied', 'Only uncompressed HTML or plain text is supported.')
        data = bytearray()
        while True:
            if time.monotonic() - started > 15:
                raise SourceImportError('source_timeout', 'The source import timed out.')
            if connection.sock:
                connection.sock.settimeout(min(8, max(.1, 15 - (time.monotonic() - started))))
            chunk = response.read1(min(65536, MAX_DOWNLOAD_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise SourceImportError('source_too_large', 'The source exceeds the 1 MiB download limit.')
        try:
            text = bytes(data).decode('utf-8')
        except UnicodeDecodeError as exc:
            raise SourceImportError('source_encoding_denied', 'This source is not valid UTF-8 text.') from exc
        if mime == 'text/html':
            parser = ArticleText()
            parser.feed(text)
            result = parser.result()
        else:
            if not text.strip() or len(text) > MAX_SOURCE_CHARS:
                raise SourceImportError('source_text_invalid', 'Source text is empty or too long.')
            result = {'text':text, 'title':'Imported source', 'published_at':None}
        return dict(result, url=canonical, publisher=parsed.hostname)
    except (OSError, http.client.HTTPException) as exc:
        raise SourceImportError('source_connection_failed', 'The source connection failed. You can paste source text instead.') from exc
    finally:
        connection.close()
