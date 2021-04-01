import unittest

import botocore
from botocore.compat import HAS_CRT

from tests.unit.auth.test_signers import (
    TestS3SigV4Auth, TestSigV4Presign, TestSigV4Resign
)

@unittest.skipIf(not HAS_CRT, "Test requires CRT to be installed.")
class TestCrtS3SigV4Auth(TestS3SigV4Auth):
    # Repeat TestS3SigV4Auth tests, but using CRT signer
    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtS3SigV4Auth

@unittest.skipIf(not HAS_CRT, "Test requires CRT to be installed.")
class TestCrtSigV4Resign(TestSigV4Resign):
    # Run same tests against CRT auth
    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtSigV4Auth

@unittest.skipIf(not HAS_CRT, "Test requires CRT to be installed.")
class TestCrtSigV4Presign(TestSigV4Presign):
    # Run same tests against CRT auth
    if HAS_CRT:
        AuthClass = botocore.crt.auth.CrtSigV4QueryAuth
