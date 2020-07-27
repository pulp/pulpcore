if [ $# -eq 0 ]; then
    echo "No arguments provided"
    exit 1
fi

# Download the schema
curl -o api.json "http://localhost:24817/pulp/api/v3/docs/api.json?bindings&plugin=$1"
# Get the version of the pulpcore or plugin as reported by status API

export VERSION=$(http :24817/pulp/api/v3/status/ | jq --arg plugin $1 -r '.versions[] | select(.component == $plugin) | .version')

podman run -u $(id -u) --rm -v ${PWD}:/local openapitools/openapi-generator-cli:v4.3.1 generate \
    -i /local/api.json \
    -g python \
    -o /local/$1-client \
    --additional-properties=packageName=pulpcore.client.$1,projectName=$1-client,packageVersion=${VERSION} \
    --skip-validate-spec \
    --strict-spec=false

mkdir -p docs/$1_client
rsync -a $1-client/docs docs/$1_client
mv $1-client/README.md docs/$1_client/README.md
rm api.json
rm -rf $1-client


cd docs/$1_client
for f in docs/*.md
do
  var=$(basename ${f%.md*})
  sed -i "1s/.*/# $var/" $f
done
