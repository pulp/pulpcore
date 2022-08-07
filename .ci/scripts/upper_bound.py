import warnings
from pkg_resources import Requirement

packages = []

try:
    with open("requirements.txt", "r") as fd:
        for line in fd.readlines():
            if not line.startswith("#"):
                req = Requirement.parse(line)
                spec = str(req.specs)
                if "~=" in spec:
                    warnings.warn(f"Please avoid using ~= on {req.name}")
                    continue
                if len(req.specs) < 2 and "==" not in spec and "<" not in spec:
                    packages.append(req.name)
except FileNotFoundError:
    # skip this test for plugins that don't use a requirements.txt
    pass

if packages:
    raise RuntimeError(
        "The following packages are missing upper bound: {}".format(", ".join(packages))
    )
