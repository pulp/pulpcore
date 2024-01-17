HOSTNAME=`hostname`

EXT_FILE=$1
EXT=$2

mkdir -p keys
mkdir -p certificates

# create client key
openssl genrsa -out keys/client.pem 2048 &> /dev/null

# create signing request for client
openssl req \
  -new \
  -key keys/client.pem \
  -out client.req \
  -nodes \
  -subj "/CN=$HOSTNAME/O=client" &> /dev/null

# sign server request w/ CA key and gen x.509 cert.
if [[ ! -z "$EXT_FILE" ]];
then
  echo "using: $EXT_FILE"
  openssl x509 \
    -req  \
    -sha1 \
    -in client.req \
    -out certificates/client.pem \
    -CA certificates/ca.pem \
    -CAkey keys/ca.pem \
    -CAcreateserial \
    -set_serial $RANDOM \
    -extfile $EXT_FILE \
    -extensions $EXT \
    -days 3650
else
  openssl x509 \
    -req  \
    -sha1 \
    -extensions usr_cert \
    -in client.req \
    -out certificates/client.pem \
    -CA certificates/ca.pem \
    -CAkey keys/ca.pem \
    -CAcreateserial \
    -set_serial $RANDOM \
    -days 3650
fi

# remove CA signing request
rm client.req
