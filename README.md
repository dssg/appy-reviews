# appy-reviews

A "smart" Web application for reviewing DSSG program application submissions

## Management

### Requirements

* docker
* pyenv-virtualenv

### Set-up

1. Create a pyenv virtualenv `appy` under Python v3.6.3:

    pyenv virtualenv 3.6.3 appy

1. Install console requirements:

    pip install -r requirement/console.txt

1. Optionally export environment variables:

* `DATABASE_URL=postgres://appy_reviews:PASSWORD@DBHOST:DBPORT/appy_reviews`
* `AWS_PROFILE`
* `AWS_EB_PROFILE`

### CLI

Project development, deployment, _etc._ are managed via `argcmdr`:

    manage --help
