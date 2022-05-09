from pkg_resources import Requirement

packages = []
with open("requirements.txt", "r") as fd:
    for line in fd.readlines():
        if not line.startswith("#"):
            req = Requirement.parse(line)
            spec = str(req.specs)
            if len(req.specs) < 2 and "~=" not in spec and "==" not in spec and "<" not in spec:
                packages.append(req.name)
if packages:
    raise RuntimeError(
        "The following packages are missing upper bound: {}".format(", ".join(packages))
    )
