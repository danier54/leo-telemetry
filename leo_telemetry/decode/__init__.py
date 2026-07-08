"""Signal Processing & Protocol Decoding.

Runs AX.25 frame synchronization, bit-destuffing, and CRC-16 FCS
validation, then strips addressing to expose the raw telemetry payload.
"""
