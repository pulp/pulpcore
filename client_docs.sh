if [ $# -eq 0 ]; then
    echo "No arguments provided"
    exit 1
fi

pip3 install m2r

# Download the schema
curl -o api.json "http://localhost:24817/pulp/api/v3/docs/api.json?bindings&plugin=$1"
# Get the version of the pulpcore or plugin as reported by status API

export VERSION=$(http :24817/pulp/api/v3/status/ | jq --arg plugin $1 -r '.versions[] | select(.component == $plugin) | .version')

docker run -u $(id -u) --rm -v ${PWD}:/local openapitools/openapi-generator-cli:v4.2.3 generate \
    -i /local/api.json \
    -g python \
    -o /local/$1-client \
    --additional-properties=packageName=pulpcore.client.$1,projectName=$1-client,packageVersion=${VERSION} \
    --skip-validate-spec \
    --strict-spec=false

m2r $1-client/README.md
sed -i "s/docs/$1-client/g" $1-client/README.rst
mv $1-client/README.rst docs/$1-client.rst
mkdir -p docs/$1-client
for f in $1-client/docs/*.md
do
  m2r $f
done
mv docs/$1-client/*.rst /tmp
mv $1-client/docs/*.rst docs/$1-client

rm api.json
mv $1-client /tmp
