set -euv

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")/../../.."

mkdir ~/.ssh
touch ~/.ssh/pulp-infra
chmod 600 ~/.ssh/pulp-infra
echo "$PULP_DOCS_KEY" > ~/.ssh/pulp-infra

echo "docs.pulpproject.org,8.43.85.236 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBGXG+8vjSQvnAkq33i0XWgpSrbco3rRqNZr0SfVeiqFI7RN/VznwXMioDDhc+hQtgVhd6TYBOrV07IMcKj+FAzg=" >> ~/.ssh/known_hosts
chmod 644 ~/.ssh/known_hosts

export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings
export PULP_SETTINGS=$PWD/.ci/ansible/settings/settings.py
export WORKSPACE=$PWD

# start the ssh agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/pulp-infra

mkdir -p ../staging-docs.pulpproject.org
tar -xvf staging-docs.pulpproject.org.tar --directory ../staging-docs.pulpproject.org
pushd ../staging-docs.pulpproject.org

# publish to pulpproject.org
rsync -avzh --delete site/ doc_builder_staging_pulp_core@docs.pulpproject.org:/var/www/docs.pulpproject.org/staging_pulp_core/

popd
