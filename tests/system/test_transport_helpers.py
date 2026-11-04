"""Small self-checks for QA's TLS, gateway and browser evidence helpers."""

import asyncio

from browser import outcomes
from cert import generate
from cryptography import x509
from cryptography.x509.oid import NameOID
from gateway import pipe


def test_certificate_is_localhost_only_and_not_a_real_service_identity(tmp_path):
    generate(tmp_path)
    certificate = x509.load_pem_x509_certificate((tmp_path / "cert.pem").read_bytes())
    assert (
        certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        == "DocuHive synthetic QA"
    )
    names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.DNSName) == ["localhost"]
    assert len(names) == 2


def test_gateway_relay_preserves_bytes_and_closes_on_eof():
    class Writer:
        def __init__(self):
            self.data, self.closed = b"", False

        def write(self, chunk):
            self.data += chunk

        async def drain(self):
            pass

        def close(self):
            self.closed = True

    async def check():
        reader = asyncio.StreamReader()
        reader.feed_data(b"synthetic\x00bytes")
        reader.feed_eof()
        writer = Writer()
        await pipe(reader, writer)
        assert writer.data == b"synthetic\x00bytes" and writer.closed

    asyncio.run(check())


def test_browser_expected_failure_skip_or_retry_is_not_accepted():
    def report(expected, statuses):
        return {
            "suites": [
                {
                    "specs": [
                        {
                            "file": "test.ts",
                            "title": "QA browser",
                            "tests": [
                                {
                                    "projectName": "mobile",
                                    "expectedStatus": expected,
                                    "results": [{"status": status} for status in statuses],
                                }
                            ],
                        }
                    ]
                }
            ]
        }

    assert set(outcomes(report("passed", ["passed"])).values()) == {"passed"}
    assert set(outcomes(report("failed", ["failed"])).values()) == {"failed"}
    assert set(outcomes(report("passed", ["failed", "passed"])).values()) == {"failed"}
    assert set(outcomes(report("skipped", ["skipped"])).values()) == {"pending"}
