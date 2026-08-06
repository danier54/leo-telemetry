import os
import sys
from pathlib import Path

from leo_telemetry.observability.exporter import start_exporter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    port = int(os.environ.get("EXPORTER_PORT", "8000"))
    print(f"Starting live exporter on port {port}")
    start_exporter(port)


if __name__ == "__main__":
    main()
