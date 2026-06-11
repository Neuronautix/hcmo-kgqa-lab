"""Application settings, read from environment / .env via pydantic-settings.

Import-safe: importing this module performs no network calls and does not
require any API keys. Paths are derived from the auto-detected repo root.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_repo_root() -> Path:
    """Walk up from this file until a repo marker is found.

    Looks for pyproject.toml, .git or the ``ontology`` asset directory.
    Falls back to three levels up (app/core/config.py -> repo root).
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
        # The ``ontology/current`` asset layout marks the repo root (avoids
        # matching the ``app/ontology`` package directory).
        if (parent / "ontology" / "current").is_dir():
            return parent
    return here.parents[2]


_REPO_ROOT = _detect_repo_root()


class Settings(BaseSettings):
    """Central configuration object.

    All fields can be overridden through environment variables (or a ``.env``
    file at the repo root). Path fields default to standard locations under
    ``REPO_ROOT`` when not explicitly supplied.
    """

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Repository root -------------------------------------------------
    REPO_ROOT: Path = Field(default=_REPO_ROOT)

    # --- Fuseki / Jena ---------------------------------------------------
    FUSEKI_BASE_URL: str = "http://localhost:3030"
    FUSEKI_DATASET: str = "hcmo"
    FUSEKI_USER: str = "admin"
    FUSEKI_PASSWORD: str = "admin"

    # --- LLM provider ----------------------------------------------------
    LLM_PROVIDER: str = "openai"  # openai|anthropic|ollama|mistral|gemini|custom
    LLM_MODEL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # --- Asset paths (derived from REPO_ROOT when unset) -----------------
    ONTOLOGY_PATH: Optional[Path] = None
    SHACL_DIR: Optional[Path] = None
    KG_EXAMPLES_DIR: Optional[Path] = None
    KG_GENERATED_DIR: Optional[Path] = None
    SPARQL_TEMPLATES_DIR: Optional[Path] = None

    # --- HCMO upstream sync layer ----------------------------------------
    # The lab vendors the canonical HCMO ontology/shapes/queries into
    # ``ontology/vendor/hcmo`` (and sibling vendor trees). These fields drive
    # scripts/sync_hcmo.py and let a single env flip switch the lab onto the
    # real HCMO once it has been reshaped. Import-safe: no network at import.
    HCMO_REPO_URL: str = "https://github.com/dhuzard/HCMO"
    HCMO_REF: str = "main"
    HCMO_VENDOR_DIR: Optional[Path] = None  # derived: REPO_ROOT/ontology/vendor/hcmo
    HCMO_ACTIVE_SOURCE: str = "synthetic"  # "synthetic" | "vendor"

    # ------------------------------------------------------------------ #
    # Derived path properties
    # ------------------------------------------------------------------ #
    def _root(self) -> Path:
        return Path(self.REPO_ROOT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ontology_path(self) -> Path:
        return self.ONTOLOGY_PATH or (self._root() / "ontology" / "current" / "hcmo.owl")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def shacl_dir(self) -> Path:
        return self.SHACL_DIR or (self._root() / "shacl")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kg_examples_dir(self) -> Path:
        return self.KG_EXAMPLES_DIR or (self._root() / "kg" / "examples")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kg_generated_dir(self) -> Path:
        return self.KG_GENERATED_DIR or (self._root() / "kg" / "generated")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sparql_templates_dir(self) -> Path:
        return self.SPARQL_TEMPLATES_DIR or (self._root() / "sparql" / "templates")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def profiles_dir(self) -> Path:
        return self._root() / "ontology" / "profiles"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def terms_json_path(self) -> Path:
        return self.profiles_dir / "hcmo_terms.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def prefixes_json_path(self) -> Path:
        return self.profiles_dir / "hcmo_prefixes.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def profile_json_path(self) -> Path:
        return self.profiles_dir / "hcmo_profile.json"

    # ------------------------------------------------------------------ #
    # HCMO sync-layer properties
    # ------------------------------------------------------------------ #
    @computed_field  # type: ignore[prop-decorator]
    @property
    def vendor_ontology_dir(self) -> Path:
        """Directory holding the vendored upstream HCMO ontology modules."""
        return self.HCMO_VENDOR_DIR or (self._root() / "ontology" / "vendor" / "hcmo")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hcmo_lock_path(self) -> Path:
        """Path to the sync lockfile recording the vendored upstream state."""
        return self._root() / "sync" / "HCMO_SYNC.lock.json"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active_ontology_path(self) -> Path:
        """The ontology the lab should treat as active.

        Defaults to the synthetic demo ontology (current behaviour). Setting
        ``HCMO_ACTIVE_SOURCE=vendor`` switches to the vendored upstream HCMO
        primary module once it has been synced/reshaped. This does NOT alter
        the default ``ontology_path`` behaviour.
        """
        if str(self.HCMO_ACTIVE_SOURCE).lower() == "vendor":
            return self.vendor_ontology_dir / "hcm.ttl"
        return self.ontology_path

    # ------------------------------------------------------------------ #
    # Fuseki endpoint properties
    # ------------------------------------------------------------------ #
    @computed_field  # type: ignore[prop-decorator]
    @property
    def query_endpoint(self) -> str:
        return f"{self.FUSEKI_BASE_URL.rstrip('/')}/{self.FUSEKI_DATASET}/sparql"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def update_endpoint(self) -> str:
        return f"{self.FUSEKI_BASE_URL.rstrip('/')}/{self.FUSEKI_DATASET}/update"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gsp_endpoint(self) -> str:
        """Graph Store Protocol endpoint."""
        return f"{self.FUSEKI_BASE_URL.rstrip('/')}/{self.FUSEKI_DATASET}/data"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def admin_endpoint(self) -> str:
        return f"{self.FUSEKI_BASE_URL.rstrip('/')}/$/datasets"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Module-level convenience instance.
settings = get_settings()
