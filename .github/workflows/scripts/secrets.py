import json
import os
import sys

secrets = json.loads(sys.argv[1])
for key, value in secrets.items():
    print(f"Setting {key} ...")
    lines = len(value.split("\n"))
    if lines > 1:
        os.system(f"/bin/bash -c \"echo '{key}<<EOF' >> $GITHUB_ENV\"")
        os.system(f"/bin/bash -c \"echo '{value}' >> $GITHUB_ENV\"")
        os.system("/bin/bash -c \"echo 'EOF' >> $GITHUB_ENV\"")
    else:
        os.system(f"/bin/bash -c \"echo '{key}={value}' >> $GITHUB_ENV\"")
