# Authenticate using Keycloak

Pulp can be configured to use authentication provided by a Keycloak server outside of Pulp.
[Keycloak](https://www.keycloak.org/) can provide Identity Brokering, User Federation, Single
sign-on, and act as a OpenID Connect-based (OIDC) Identity Provider.



## Required Python Modules

The library that will be utilized for the integration between Keycloak and Pulp is
[python-social-auth](https://python-social-auth.readthedocs.io/en/latest/index.html). The
following python modules must be installed in order to make use of python-social-auth within Pulp:

```bash
social-auth-core
social-auth-app-Django
```



## Python Social Auth and Django

The [python-social-auth documentation](https://python-social-auth.readthedocs.io/en/latest/configuration/django.html)
describes the django updates necessary to configure social-auth.

Enable general python social integration with the following steps:

### 1. Add the application to INSTALLED_APPS

```python title="settings.py"
INSTALLED_APPS = (
   ...
   'social_django',
   ...
)
```

### 2. Accept Keycloak auth

Accept Keycloak auth instead of checking the internal users database by enabling:

```python title="settings.py"
AUTHENTICATION_BACKENDS = [
   ...
   'social_core.backends.keycloak.KeycloakOAuth2',
   ...
]
```

### 3. Update the context processor

Update the context processor that will add backends and associations data to the template context:

```python title="settings.py"
TEMPLATES = [
   {
       ...
       'OPTIONS': {
           ...
           'context_processors': [
               ...
               'social_django.context_processors.backends',
               'social_django.context_processors.login_redirect',
               ...
           ]
       }
   }
]
```

### 4. Define the authentication pipeline

Define the authentication pipeline for data that will be associated with users:

```python title="settings.py"
SOCIAL_AUTH_PIPELINE = (
   'social_core.pipeline.social_auth.social_details',
   'social_core.pipeline.social_auth.social_uid',
   'social_core.pipeline.social_auth.social_user',
   'social_core.pipeline.user.get_username',
   'social_core.pipeline.social_auth.associate_by_email',
   'social_core.pipeline.user.create_user',
   'social_core.pipeline.social_auth.associate_user',
   'social_core.pipeline.social_auth.load_extra_data',
   'social_core.pipeline.user.user_details',
)
```



## Python Social Auth and Keycloak

The python-social-auth keycloak backend
[documentation](https://python-social-auth.readthedocs.io/en/latest/backends/keycloak.html#keycloak-open-source-red-hat-sso)
describes the necessary Keycloak integration variables.

Enable python social and Keycloak integration with the following steps:

1) On your Keycloak server, create a Realm (pulp)

2) Create a Client in the new Realm

3) Configure the Client `Access Type` to be "confidential.

Provide `` Valid Redirect URIs` `` with
 `http://<pulp-hostname>:<port>/*`. Set the `User Info Signed Response Algorithm` and
 `Request Object Signature Algorithm` is set to `RS256` in the
 `Fine Grain OpenID Connect Configuration` section

4) In the Pulp settings, add the value for the `Client ID`:

 ```
 SOCIAL_AUTH_KEYCLOAK_KEY = '<Client ID>'
 ```

5) Gather the `Client Secret` for the Pulp settings. You can find the `Client Secret` in the
   Credentials tab:

 ```
 SOCIAL_AUTH_KEYCLOAK_SECRET = '<Client Secret>'
 ```

6) Collect the `Public Key` from the Realm's Keys tab:

 ```
 SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY = '<Public Key>'
 ```

7) Add the `authorization_endpoint` and `token_endpoint` URL that you find to the Realm OpenID Endpoint
   Configuration to the Pulp settings:

 ```
 SOCIAL_AUTH_KEYCLOAK_AUTHORIZATION_URL = \
     'https://iam.example.com/auth/realms/pulp/protocol/openid-connect/auth/'
 SOCIAL_AUTH_KEYCLOAK_ACCESS_TOKEN_URL = \
     'https://iam.example.com/auth/realms/pulp/protocol/openid-connect/token/'
 ```

8) Create an audience mapper for the JWT token.

In the Client, select the Mappers tab, select the Create button to create a Mapper. Name the mapper, for example, "Audience Mapper".
From the `Mapper Type` list, select "Audience". Define the `Included Client Audience` to be the `Client ID`.
Enable this for both the ID token and access token.

9) Add additional Built-in Mappers to the JWT to populate the token with the data defined in the Social Auth Pipeline.
  
To do this, in the Client again select the Mappers tab. Next select the
"Add Builtin" button and you will be presented with a table of mappers that can be chosen.
Common choices are `username`, `email`, `groups`, `given name`, `family name`,
`full name`, `updated at`, and `email verified`.

After setup is completed go to: `http://<pulp-hostname>:<port>/login/keycloak` and the login flow
will be presented.
