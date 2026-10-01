from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / 'data'
    allowed_origins: tuple[str, ...] = ('http://127.0.0.1:8000', 'http://localhost:8000', 'http://testserver')
    secure_cookies: bool = False
    session_seconds: int = 8 * 60 * 60
    max_asset_bytes: int = 10 * 1024 * 1024

    @classmethod
    def from_env(cls):
        production = os.getenv('STUDIO_ENV', 'development') == 'production'
        origins = tuple(x.strip() for x in os.getenv('STUDIO_ALLOWED_ORIGINS', 'http://127.0.0.1:8000,http://localhost:8000').split(',') if x.strip())
        if not origins:
            raise ValueError('At least one exact allowed origin is required')
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password or '*' in origin:
                raise ValueError('Allowed origins must be exact http(s) origins')
            if production and parsed.scheme != 'https':
                raise ValueError('Production requires HTTPS origins')
            if not production and parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                raise ValueError('Development HTTP origins must be loopback addresses')
        return cls(data_dir=Path(os.getenv('STUDIO_DATA_DIR', str(ROOT / 'data'))).resolve(), allowed_origins=origins, secure_cookies=production)
