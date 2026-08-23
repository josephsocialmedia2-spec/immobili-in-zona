import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def default_home() -> Path:
    configured = os.getenv("F1_IR_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return root / "F1IndirizzoRemoto"
    return Path.home() / ".local" / "share" / "f1-indirizzo-remoto"


@dataclass(frozen=True)
class Settings:
    home: Path
    host: str
    port: int
    secret_key: str
    max_upload_bytes: int
    site_url: str

    @property
    def database_path(self) -> Path:
        return self.home / "data" / "f1_indirizzo_remoto.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.home / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.home / "exports"

    @property
    def letters_dir(self) -> Path:
        return self.home / "letters"

    @property
    def backups_dir(self) -> Path:
        return self.home / "backups"

    @property
    def diagnostics_dir(self) -> Path:
        return self.home / "diagnostics"

    def ensure_directories(self) -> None:
        for path in (
            self.database_path.parent,
            self.uploads_dir,
            self.exports_dir,
            self.letters_dir,
            self.backups_dir,
            self.diagnostics_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    home = default_home()
    secret_file = home / ".local-secret"
    secret = os.getenv("F1_IR_SECRET_KEY", "").strip()
    if not secret:
        home.mkdir(parents=True, exist_ok=True)
        if secret_file.exists():
            secret = secret_file.read_text(encoding="utf-8").strip()
        else:
            secret = secrets.token_urlsafe(48)
            secret_file.write_text(secret, encoding="utf-8")
            try:
                secret_file.chmod(0o600)
            except OSError:
                pass
    settings = Settings(
        home=home,
        host=os.getenv("F1_IR_HOST", "127.0.0.1"),
        port=int(os.getenv("F1_IR_PORT", "8765")),
        secret_key=secret,
        max_upload_bytes=int(os.getenv("F1_IR_MAX_UPLOAD_MB", "15")) * 1024 * 1024,
        site_url=os.getenv("F1_IR_SITE_URL", "https://f1immobiliare.com").rstrip("/"),
    )
    settings.ensure_directories()
    return settings
