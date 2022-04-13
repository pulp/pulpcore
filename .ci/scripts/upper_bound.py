from pkg_resources import Requirement

packages = []
with open("requirements.txt", "r") as fd:
    for line in fd.readlines():
        req = Requirement.parse(line)
        if len(req.specs) < 2 and "~=" not in str(req.specs) and "==" not in str(req.specs):
            packages.append(req.name)
if packages:
    raise RuntimeError(
        "The following packages are missing upper bound: {}".format(", ".join(packages))
    )
