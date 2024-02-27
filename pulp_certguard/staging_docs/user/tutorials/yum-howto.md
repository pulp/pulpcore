# Configure yum/dnf

To enable yum/dnf to access content protected by a content-guard, use the following as a guide. These are
essentially all you need to end up with a protected rpm repo.

Working through these guides will help to make sense of
all the steps and how they relate to each other.

[pulp_rpm Create/Sync/Publish](site:/pulp_rpm/docs/user/tutorials/01-create_sync_publish/)

[Certguard on GitHub](https://github.com/pulp/pulp-certguard)

[EasyRSA](https://github.com/OpenVPN/easy-rsa/blob/master/README.quickstart.md)

## easy_rsa setup

Once you get the easy_rsa rpm installed, copy the skeleton of scripts to where you want your cert infra to live.
The quickstart guide is easy to follow.

If you keep everything in a local git repo, you can do reverts/diffs while learning new things.

```bash
cp -r /usr/share/easy-rsa .
cd easy-rsa
git init
git add *
git commit -m 'pristine start' -a
cd 3
./easyrsa init-pki
 ./easyrsa build-ca
# now convert your crt to a pem
# you will use this later as a content guard in pulp
cd pki
openssl x509 -in ca.crt -out ca.pem -outform PEM
cd ..
# now generate a client cert
# you're going to do this on the server with the ca.
# the guide recommends not doing this, I keep everything in one place.
# The reason for this, is that pulp only will need a signed pem. No key, not csr, nothing else.
# So, I will generate a yum-client cert and sign it here. Then I'll copy the pem to the client machines.
# later, this will be automated via ansible.

./easyrsa gen-req yum-client
# now sign it so its trusted
./easyrsa sign-req client yum-client
# now convert it to pem format
openssl x509 -in pki/issued/yum-client.crt  -out pki/issued/yum-client.pem -outform PEM
```

## pulp setup

NB:
The single biggest tip here is this:

When a rest call returns a task id (uuid), you need to poll for
it. The async tasks don't log to disk. Errors will show up in the task
details.

I had a ton of self inflicted problems due to doing this on a CIS
hardened image where the default umask leads to non-shared
directories/files when created (default 750 instead of 755 dirs, etc).
All the permission denied errors showed up fine in the tasks, but i
didn't immediately know to check there and wasted some time.

```bash
# this is all in the pulp workflow as linked to above.
# create repo
http POST http://localhost:24817/pulp/api/v3/repositories/ name=boomi-epel

# Lookup the thing we just made
export REPO_HREF=$(http http://localhost:24817/pulp/api/v3/repositories/ | jq -r '.results[] | select(.name == "boomi-epel") | .pulp_href')

# create new remote
http POST http://localhost:24817/pulp/api/v3/remotes/rpm/rpm/ name='boomi-epel-remote' url='file:///usr/local/lib/pulp/staging/epel/' policy='immediate'

export REMOTE_HREF=$(http :24817/pulp/api/v3/remotes/rpm/rpm/ | jq -r '.results[] | select(.name == "boomi-epel-remote") | .pulp_href')

# Sync the repo
http POST http:/localhost:24817${REMOTE_HREF}sync/ repository=$REPO_HREF
# {
#     "task": "/pulp/api/v3/tasks/abb42ba7-77f9-49c4-af05-3af407ab8596/"
# }

# Inspect the new thingy....
http GET http://localhost:24817${REPO_HREF}versions/1/

# Create a publication
http POST http://localhost:24817/pulp/api/v3/publications/rpm/rpm/ repository=$REPO_HREF

# get repo-version (display/informational)
export PUBLICATION_HREF=$(http :24817/pulp/api/v3/publications/rpm/rpm/ | jq -r '.results[] | select(.repository_version|test("'$REPO_HREF'.")) | .pulp_href')

http POST http://localhost:24817/pulp/api/v3/distributions/rpm/rpm/ name='boomi-epel-distro' base_path='boomi-epel' publication=$PUBLICATION_HREF

#Follow the task progress here:
http GET http://localhost:24817/pulp/api/v3/tasks/
http GET http://localhost:24817/pulp/api/v3/tasks/uuid-of-single-task-for-reasonable-responses

# THe CONTENT_HOST setting is super important for this. Set it to something valid.

# View all the published stats
http GET http://localhost:24817/pulp/api/v3/distributions/rpm/rpm/

# Get the repo metadata from the published end point on the yum side
http GET  http://localhost:24816/pulp/content/boomi-epel-2/repodata/repomd.xml
```

## certguard setup

The ca.pem and the yum-client.pem from above are needed for this part.

Before you do this, make sure your non-protected repo works. I just
configured it on localhost and installed a sample rpm from my private
epel mirror.

Alternatively, just check that yum makecache works. If it doesn't,
troubleshoot it til it does. Then we can add protection.

```bash
# This is the essence of the guide for certguard linked to above. See that for better docs.

http --form POST http://localhost:8000/pulp/api/v3/contentguards/certguard/x509/ name=boomi-ca ca_certificate@/var/lib/pulp-certs/easy-rsa/3/pki/ca.pem

export GUARD_HREF=$(http localhost:24817/pulp/api/v3/contentguards/certguard/x509/?name=boomi-ca | jq -r '.results[0].pulp_href')

# protect one
http PATCH http://localhost:24817/pulp/api/v3/distributions/rpm/rpm/4d9ef794-4af1-44ba-be5e-607defd396de/ content_guard=$GUARD_HREF
```

## yum setup

Now that we're here, lets teach yum how to jam a signed cert in the
right http header when accessing one of our custom repos.

```bash
# Show that the now protected repo wont let us in.
# confirm it denies the yum process
[root@ip-10-76-7-46 ~]# yum makecache
Loaded plugins: amazon-id, rhui-lb, search-disabled-repos
http://localhost:24816/pulp/content/boomi-epel-2/repodata/repomd.xml: [Errno 14] HTTP Error 403 - Forbidden
Trying other mirror.
To address this issue please refer to the below knowledge base article

https://access.redhat.com/solutions/69319

If above article doesn't help to resolve this issue please open a ticket with Red Hat Support.

Metadata Cache Created
[root@ip-10-76-7-46 ~]#

cp $PATH_TO_EASYRSA/yum-client.pem /etc/boomi/yum.pem

# Install my certguard plugin
copy to /usr/lib/yum-plugins

# enable the plugin within yum
update /etc/yum/pluginconf.d/certguard.conf
[main]
enabled=1


# kick the tires
[root@ip-10-76-7-46 yum-plugins]# yum makecache
Loaded plugins: amazon-id, certguard, rhui-lb, search-disabled-repos
boomi-epel                                                                                                        | 3.5 kB  00:00:00
(1/4): boomi-epel/updateinfo                                                                                      |   71 B  00:00:00
(2/4): boomi-epel/filelists                                                                                       |  11 MB  00:00:00
(3/4): boomi-epel/primary                                                                                         | 3.7 MB  00:00:00
(4/4): boomi-epel/other                                                                                           | 2.3 MB  00:00:00
boomi-epel                                                                                                                   13215/13215
boomi-epel                                                                                                                   13215/13215
boomi-epel                                                                                                                   13215/13215
Metadata Cache Created
[root@ip-10-76-7-46 yum-plugins]#

NB: Make sure the cert paths are right.
Make sure the repo names begin with the right prefix
```
