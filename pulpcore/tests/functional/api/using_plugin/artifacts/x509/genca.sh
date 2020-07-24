HOSTNAME=`hostname`

EXT_FILE=$1
EXT=$2

mkdir -p keys
mkdir -p certificates

# create CA key
openssl genrsa -out keys/ca.pem 2048 &> /dev/null

# create the CA signing request.
openssl req \
  -new \
  -sha1 \
  -days 7035 \
  -key keys/ca.pem \
  -out ca.req \
  -subj "/CN=$HOSTNAME"

# create the CA certificate
if [[ ! -z "$EXT_FILE" ]];
then
  echo "using: $EXT_FILE"
  openssl x509 \
    -req \
    -days 7035 \
    -sha1 \
    -extfile $EXT_FILE  \
    -extensions $EXT \
    -signkey keys/ca.pem \
    -in ca.req \
    -out certificates/ca.pem &> /dev/null
else
  openssl x509 \
    -req \
    -days 7035 \
    -sha1 \
    -extensions v3_ca  \
    -signkey keys/ca.pem \
    -in ca.req \
    -out certificates/ca.pem &> /dev/null
fi

# remove CA signing request
rm ca.req
