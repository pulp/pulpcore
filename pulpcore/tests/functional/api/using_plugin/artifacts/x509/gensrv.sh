HOSTNAME=`hostname`

EXT_FILE=$1
EXT=$2

mkdir -p keys
mkdir -p certificates

# create client key
openssl genrsa -out keys/server.pem 2048 &> /dev/null

# create signing request
openssl req \
  -new \
  -key keys/server.pem \
  -out server.req \
  -nodes \
  -subj "/CN=$HOSTNAME/O=server" &> /dev/null

# sign server request w/ CA key and gen x.509 cert.
if [[ ! -z "$EXT_FILE" ]];
then
  echo "using: $EXT_FILE"
  openssl x509 \
    -req  \
    -days 7035 \
    -extfile $EXT_FILE \
    -extensions $EXT \
    -in server.req \
    -out certificates/server.pem \
    -sha1 \
    -CA certificates/ca.pem \
    -CAkey keys/ca.pem \
    -CAcreateserial \
    -set_serial $RANDOM
    -subj "/CN=$HOSTNAME" &> /dev/null
else
  openssl x509 \
    -req  \
    -days 7035 \
    -extensions usr_cert \
    -in server.req \
    -out certificates/server.pem \
    -sha1 \
    -CA certificates/ca.pem \
    -CAkey keys/ca.pem \
    -CAcreateserial \
    -set_serial $RANDOM
    -subj "/CN=$HOSTNAME" &> /dev/null
fi

# remove CA signing request
rm server.req
