import asyncio
from pathlib import Path


class LocalDocumentStorage:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    async def save(self, document_id: str, filename: str, content: bytes) -> str:
        # Ignoramos el nombre del cliente para el path (evita path traversal).
        target = self._base / document_id / "original.pdf"

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        await asyncio.to_thread(_write)  # no bloquea el event loop
        return str(target)
