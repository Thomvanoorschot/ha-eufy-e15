"""The key script's crypto against fixed reference values. No network."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "tools" / "get-local-key.sh"

EXPECTED = [
    # tuya_password("eh-0123456789abcdef0123456789abcdef01234567")
    "18d556a1cca09f1390c5bde2cca29269",
    # tuya_sign of the fixed parameters in the script's self-test
    "d725f29f5fb3cdb959fee661dabd8984f8b5623dae9e0cd6fd68871e41624945",
    # raw RSA of a 32-byte plaintext with exponent 65537 and modulus 2^1023 + 1234567
    "61c213e56bd538a4bf2b3b9ad392148ae49281fbaf9a7d0852ca6f0415361a0134a87eae6f23fb7a"
    "dddcfb05e91b85ea895cf4eb4ae37da6937eae2d879424c8da11ab8c3fec680abae2495bb31c290b"
    "ac1dfd43ccfc0fb8dfd0c1d130918d53cce88fca628a94f2dc6c86c03de342eca59ca6f810e3e88b"
    "e5a165c02994fa19",
]


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("bash", "openssl", "bc", "jq", "xxd", "uuidgen")),
    reason="system tools missing",
)
def test_self_test_matches_reference() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--self-test"], capture_output=True, text=True, check=True
    )
    assert result.stdout.split() == EXPECTED
