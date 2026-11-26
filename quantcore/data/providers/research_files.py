"""Local research imports of licensed market history, isolated from broker routing."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from quantcore.core.models import AssetClass, Bar
from quantcore.information.store import now, publish, read_snapshot


class FileInstrument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(pattern=r"^[A-Z0-9._-]{1,20}$")
    name: str = Field(min_length=1, max_length=80)
    asset_class: AssetClass
    currency: Literal["USD", "KRW"]
    exchange_timezone: str
    source: str = Field(min_length=1, max_length=120)
    volume_unit: str = Field(min_length=1, max_length=40)
    license_note: str = Field(min_length=1, max_length=240)


def import_csv(directory, metadata, path):
    spec = FileInstrument.model_validate(metadata)
    ZoneInfo(spec.exchange_timezone)
    cutoff = datetime.now(timezone.utc)
    bars = {}
    with Path(path).open(newline="") as handle:
        for i, row in enumerate(csv.DictReader(handle)):
            if i >= 10000:
                raise ValueError("import exceeds 10,000 rows")
            bar = Bar.model_validate({**row, "symbol": spec.symbol, "source": spec.source,
                                      "currency": spec.currency, "mode": "historical"})
            if bar.available_at > cutoff or bar.timestamp in bars:
                raise ValueError("future availability or duplicate observation")
            bars[bar.timestamp] = bar.model_dump(mode="json")
    if not bars:
        raise ValueError("empty research import")
    kind = "import-" + spec.symbol
    return publish(directory, kind, {"instrument.json": spec.model_dump(mode="json"),
                                     "bars.json": [bars[key] for key in sorted(bars)]},
                   {"collected_at": now(), "bars": len(bars)})


def catalog(directory):
    root = Path(directory)/"information"
    return [path.name[7:] for path in sorted(root.glob("import-*")) if (path/"latest.json").is_file()]


def series(directory, symbol):
    snapshot = read_snapshot(directory, "import-" + symbol)
    if not snapshot:
        return {"status": "unavailable", "reason": "no local source file for this instrument"}
    root, manifest = snapshot
    return {"status": "ok", "metadata": json.loads((root/"instrument.json").read_text()),
            "bars": json.loads((root/"bars.json").read_text())[-252:], "collected_at": manifest["collected_at"]}
