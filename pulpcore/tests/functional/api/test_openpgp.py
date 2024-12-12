import pytest


ALICE_PUB = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Alice's OpenPGP certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

mDMEXEcE6RYJKwYBBAHaRw8BAQdArjWwk3FAqyiFbFBKT4TzXcVBqPTB3gmzlC/U
b7O1u120JkFsaWNlIExvdmVsYWNlIDxhbGljZUBvcGVucGdwLmV4YW1wbGU+iJAE
ExYIADgCGwMFCwkIBwIGFQoJCAsCBBYCAwECHgECF4AWIQTrhbtfozp14V6UTmPy
MVUMT0fjjgUCXaWfOgAKCRDyMVUMT0fjjukrAPoDnHBSogOmsHOsd9qGsiZpgRnO
dypvbm+QtXZqth9rvwD9HcDC0tC+PHAsO7OTh1S1TC9RiJsvawAfCPaQZoed8gK4
OARcRwTpEgorBgEEAZdVAQUBAQdAQv8GIa2rSTzgqbXCpDDYMiKRVitCsy203x3s
E9+eviIDAQgHiHgEGBYIACAWIQTrhbtfozp14V6UTmPyMVUMT0fjjgUCXEcE6QIb
DAAKCRDyMVUMT0fjjlnQAQDFHUs6TIcxrNTtEZFjUFm1M0PJ1Dng/cDW4xN80fsn
0QEA22Kr7VkCjeAEC08VSTeV+QFsmz55/lntWkwYWhmvOgE=
=iIGO
-----END PGP PUBLIC KEY BLOCK-----
"""


ALICE_REVOCATION = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Alice's revocation certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

iHgEIBYIACAWIQTrhbtfozp14V6UTmPyMVUMT0fjjgUCXaWkOwIdAAAKCRDyMVUM
T0fjjoBlAQDA9ukZFKRFGCooVcVoDVmxTaHLUXlIg9TPh2f7zzI9KgD/SLNXUOaH
O6TozOS7C9lwIHwwdHdAxgf5BzuhLT9iuAM=
=Tm8h
-----END PGP PUBLIC KEY BLOCK-----
"""


ALICE_REVOKED = """
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEXEcE6RYJKwYBBAHaRw8BAQdArjWwk3FAqyiFbFBKT4TzXcVBqPTB3gmzlC/U
b7O1u12IeAQgFggAIBYhBOuFu1+jOnXhXpROY/IxVQxPR+OOBQJdpaQ7Ah0AAAoJ
EPIxVQxPR+OOgGUBAMD26RkUpEUYKihVxWgNWbFNoctReUiD1M+HZ/vPMj0qAP9I
s1dQ5oc7pOjM5LsL2XAgfDB0d0DGB/kHO6EtP2K4A7QmQWxpY2UgTG92ZWxhY2Ug
PGFsaWNlQG9wZW5wZ3AuZXhhbXBsZT6IkAQTFggAOAIbAwULCQgHAgYVCgkICwIE
FgIDAQIeAQIXgBYhBOuFu1+jOnXhXpROY/IxVQxPR+OOBQJdpZ86AAoJEPIxVQxP
R+OO6SsA+gOccFKiA6awc6x32oayJmmBGc53Km9ub5C1dmq2H2u/AP0dwMLS0L48
cCw7s5OHVLVML1GImy9rAB8I9pBmh53yArg4BFxHBOkSCisGAQQBl1UBBQEBB0BC
/wYhratJPOCptcKkMNgyIpFWK0KzLbTfHewT356+IgMBCAeIeAQYFggAIBYhBOuF
u1+jOnXhXpROY/IxVQxPR+OOBQJcRwTpAhsMAAoJEPIxVQxPR+OOWdABAMUdSzpM
hzGs1O0RkWNQWbUzQ8nUOeD9wNbjE3zR+yfRAQDbYqvtWQKN4AQLTxVJN5X5AWyb
Pnn+We1aTBhaGa86AQ==
=W1yt
-----END PGP PUBLIC KEY BLOCK-----
"""


BOB_PUB = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Bob's OpenPGP certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

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
NEJd3XZRzaXZE2aAMQ==
=NXei
-----END PGP PUBLIC KEY BLOCK-----
"""

BOB_REVOCATION = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Bob's revocation certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

iQG2BCABCgAgFiEE0aZuGiOxgsmYD3iM+/zIKgFeczAFAl2lnQQCHQAACgkQ+/zI
KgFeczAIHAv/RrlGlPFKsW0BShC8sVtPfbT1N9lUqyrsgBhrUryM/i+rBtkbnSjp
28R5araupt0og1g2L5VsCRM+ql0jf0zrZXOorKfAO70HCP3X+MlEquvztMUZGJRZ
7TSMgIY1MeFgLmOw9pDKf3tSoouBOpPe5eVfXviEDDo2zOfdntjPyCMlxHgAcjZo
XqMaurV+nKWoIx0zbdpNLsRy4JZcmnOSFdPw37R8U2miPi2qNyVwcyCxQy0LjN7Y
AWadrs9vE0DrneSVP2OpBhl7g+Dj2uXJQRPVXcq6w9g5Fir6DnlhekTLsa78T5cD
n8q7aRusMlALPAOosENOgINgsVcjuILkPN1eD+zGAgHgdiKaep1+P3pbo5n0CLki
UCAsLnCEo8eBV9DCb/n1FlI5yhQhgQyMYlp/49H0JSc3IY9KHhv6f0zIaRWs0JuD
ajcXTJ9AyB+SA6GBb9Q+XsNXjZ1gj75ekUD1sQ3ezTvVfovgP5bD+vPvILhSImKB
aU6V3zld/x/1
=mMwU
-----END PGP PUBLIC KEY BLOCK-----
"""


@pytest.mark.parallel
def test_key_upload(tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task):
    keyring = openpgp_keyring_factory()

    alice_pub = tmpdir / "alice.pub"
    alice_pub.write_text(ALICE_PUB, "UTF-8")

    alice_revoked = tmpdir / "alice.revoked"
    alice_revoked.write_text(ALICE_REVOKED, "UTF-8")

    bob_pub = tmpdir / "bob.pub"
    bob_pub.write_text(BOB_PUB, "UTF-8")

    result = pulpcore_bindings.ContentOpenpgpPublickeyApi.create(
        file=str(alice_pub), repository=keyring.pulp_href
    )
    monitor_task(result.task)
    result = pulpcore_bindings.ContentOpenpgpPublickeyApi.create(
        file=str(bob_pub), repository=keyring.pulp_href
    )
    monitor_task(result.task)
    result = pulpcore_bindings.ContentOpenpgpPublickeyApi.create(
        file=str(alice_revoked), repository=keyring.pulp_href
    )
    monitor_task(result.task)
