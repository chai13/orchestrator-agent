"""
Generic Chunked Message Protocol

Splits large messages into chunk protocol messages and reassembles them
on the receiving side. Transport-agnostic: each controller defines how
to actually send the chunks over its channel.

Chunk protocol:
    { "type": "chunk_start", "transfer_id": ..., "total_chunks": N, "total_size": N }
    { "type": "chunk_data",  "transfer_id": ..., "sequence": N, "data": "..." }
    { "type": "chunk_end",   "transfer_id": ... }
"""

import json
import math
import time
from typing import Optional

from tools.logger import log_info, log_warning

# Messages smaller than this (chars) are sent directly
CHUNK_THRESHOLD = 15_000

# Max payload per chunk_data message (chars, leaves room for JSON wrapper)
CHUNK_PAYLOAD_SIZE = 14_000

# Stale transfer timeout (seconds)
STALE_TRANSFER_TIMEOUT = 60

_transfer_counter = 0


def _next_transfer_id() -> str:
    global _transfer_counter
    _transfer_counter = (_transfer_counter + 1) % 1_000_000
    return f"{int(time.time() * 1000)}-{_transfer_counter}"


def split_into_chunks(message: str) -> list[str]:
    """
    Split a message string into chunk protocol messages.

    If the message is smaller than CHUNK_THRESHOLD, returns a single-element
    list containing the original message (zero overhead).

    If the message is large, returns a list of JSON strings:
    [chunk_start, chunk_data_0, chunk_data_1, ..., chunk_end]

    Args:
        message: The full message string to (potentially) split.

    Returns:
        List of strings ready to be sent over any transport.
    """
    if len(message) < CHUNK_THRESHOLD:
        return [message]

    transfer_id = _next_transfer_id()
    total_chunks = math.ceil(len(message) / CHUNK_PAYLOAD_SIZE)

    log_info(f"Splitting message into chunks: {len(message)} chars, {total_chunks} chunks")

    chunks: list[str] = []

    # chunk_start
    chunks.append(json.dumps({
        "type": "chunk_start",
        "transfer_id": transfer_id,
        "total_chunks": total_chunks,
        "total_size": len(message),
    }))

    # chunk_data
    for seq in range(total_chunks):
        start = seq * CHUNK_PAYLOAD_SIZE
        data = message[start:start + CHUNK_PAYLOAD_SIZE]
        chunks.append(json.dumps({
            "type": "chunk_data",
            "transfer_id": transfer_id,
            "sequence": seq,
            "data": data,
        }))

    # chunk_end
    chunks.append(json.dumps({
        "type": "chunk_end",
        "transfer_id": transfer_id,
    }))

    return chunks


class ChunkReassembler:
    """
    Reassembles chunked messages received over any transport.

    Feed each incoming parsed message via handle_chunk_message().
    Returns the complete reassembled string when chunk_end arrives,
    or None if the message is a partial chunk.
    """

    CHUNK_TYPES = frozenset(("chunk_start", "chunk_data", "chunk_end"))

    def __init__(self):
        self._transfers: dict[str, dict] = {}

    def is_chunk_message(self, msg_type: str) -> bool:
        """Returns True if the message type is a chunk protocol message."""
        return msg_type in self.CHUNK_TYPES

    def handle_chunk_message(self, message: dict) -> Optional[str]:
        """
        Process a chunk protocol message.

        Returns the fully reassembled message string when complete,
        or None if still accumulating.
        """
        msg_type = message.get("type")
        transfer_id = message.get("transfer_id")

        if msg_type == "chunk_start":
            total_chunks = message["total_chunks"]
            self._transfers[transfer_id] = {
                "chunks": [None] * total_chunks,
                "received": 0,
                "total_chunks": total_chunks,
                "total_size": message["total_size"],
                "started_at": time.time(),
            }
            log_info(
                f"Chunk transfer started: {transfer_id} "
                f"({total_chunks} chunks, {message['total_size']} bytes)"
            )
            return None

        if msg_type == "chunk_data":
            transfer = self._transfers.get(transfer_id)
            if not transfer:
                log_warning(f"Received chunk_data for unknown transfer: {transfer_id}")
                return None
            transfer["chunks"][message["sequence"]] = message["data"]
            transfer["received"] += 1
            return None

        if msg_type == "chunk_end":
            transfer = self._transfers.pop(transfer_id, None)
            if not transfer:
                log_warning(f"Received chunk_end for unknown transfer: {transfer_id}")
                return None
            assembled = "".join(transfer["chunks"])
            elapsed = time.time() - transfer["started_at"]
            log_info(
                f"Chunk transfer complete: {transfer_id} "
                f"({len(assembled)} bytes in {elapsed:.1f}s)"
            )
            return assembled

        return None

    def cleanup_stale(self, timeout: float = STALE_TRANSFER_TIMEOUT) -> None:
        """Remove transfers that have been in-flight longer than timeout seconds."""
        now = time.time()
        stale = [
            tid for tid, t in self._transfers.items()
            if now - t["started_at"] > timeout
        ]
        for tid in stale:
            log_warning(f"Cleaning up stale chunk transfer: {tid}")
            del self._transfers[tid]
