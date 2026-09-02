from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "mp_catalog.csv"
)
_MP_CODE_PATTERN = re.compile(r"^(?:MP\s*)?(\d{1,3})$", re.IGNORECASE)


class InvalidMPCodeError(ValueError):
    """Raised when an input does not have a supported MP code format."""


class MPCodeNotFoundError(LookupError):
    """Raised when an MP code is absent from the internal catalog."""

    def __init__(self, input_mp_code: str) -> None:
        self.input_mp_code = input_mp_code
        super().__init__(
            f"MP code {input_mp_code!r} does not exist in the internal catalog; "
            "no fallback was used"
        )


class MPCatalogFormatError(ValueError):
    """Raised when the internal catalog cannot be read without inference."""


@dataclass(frozen=True, slots=True)
class ResolvedMaterial:
    """Internal trace record produced by an exact catalog lookup."""

    input_mp_code: str
    catalog_mp_code: str
    product_name: str


def normalize_mp_code(input_mp_code: str) -> str:
    """Normalize accepted user forms to the catalog form ``MP 000``."""

    if not isinstance(input_mp_code, str):
        raise InvalidMPCodeError("MP code must be text")

    match = _MP_CODE_PATTERN.fullmatch(input_mp_code.strip())
    if match is None:
        raise InvalidMPCodeError(
            f"Unsupported MP code format: {input_mp_code!r}"
        )
    return f"MP {match.group(1).zfill(3)}"


class MPCodeResolver:
    """Resolve internal MP codes using only the company-owned CSV catalog."""

    def __init__(self, catalog_path: str | Path = DEFAULT_CATALOG_PATH) -> None:
        self.catalog_path = Path(catalog_path)
        self._products_by_code = self._load_catalog()

    def _load_catalog(self) -> dict[str, tuple[str, str]]:
        products_by_code: dict[str, tuple[str, str]] = {}

        try:
            catalog_file = self.catalog_path.open(
                "r", encoding="utf-8-sig", newline=""
            )
        except OSError as error:
            raise MPCatalogFormatError(
                f"Could not read internal MP catalog: {self.catalog_path}"
            ) from error

        with catalog_file:
            reader = csv.DictReader(catalog_file)
            if reader.fieldnames != ["mp_code", "product_name"]:
                raise MPCatalogFormatError(
                    "Internal MP catalog must contain exactly the columns "
                    "mp_code and product_name"
                )

            for line_number, row in enumerate(reader, start=2):
                raw_code = row["mp_code"]
                product_name = row["product_name"]
                if raw_code is None or product_name is None or not product_name.strip():
                    raise MPCatalogFormatError(
                        f"Incomplete internal MP catalog row at line {line_number}"
                    )

                try:
                    normalized_code = normalize_mp_code(raw_code)
                except InvalidMPCodeError as error:
                    raise MPCatalogFormatError(
                        f"Invalid mp_code at catalog line {line_number}"
                    ) from error

                existing = products_by_code.get(normalized_code)
                if existing is not None and existing[1] != product_name:
                    raise MPCatalogFormatError(
                        f"Conflicting catalog entries for {normalized_code}"
                    )
                products_by_code[normalized_code] = (raw_code, product_name)

        return products_by_code

    def resolve(self, input_mp_code: str) -> ResolvedMaterial:
        normalized_code = normalize_mp_code(input_mp_code)
        catalog_entry = self._products_by_code.get(normalized_code)
        if catalog_entry is None:
            raise MPCodeNotFoundError(input_mp_code)

        catalog_mp_code, product_name = catalog_entry
        return ResolvedMaterial(
            input_mp_code=input_mp_code,
            catalog_mp_code=catalog_mp_code,
            product_name=product_name,
        )


def build_external_search_query(resolved_material: ResolvedMaterial) -> str:
    """Return the only material identifier allowed at the search boundary."""

    return resolved_material.product_name
