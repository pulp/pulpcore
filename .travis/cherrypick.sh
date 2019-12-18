pip install PyGithub GitPython yq

export STABLE_BRANCH=$(yq -r ".stable_branch" template_config.yml)

python ./.travis/cherrypick.py
