# appy-reviews

Appy is a "smart" Web application for reviewing DSSG program application submissions.

## Management

### Assumptions

The below dependencies are not strict requirements, but they are strongly recommended and assumed.

#### Docker

Appy is developed against and deployed via [Docker](https://www.docker.com/).

#### pyenv

[pyenv](https://github.com/pyenv/pyenv) is a great development tool for managing versions of Python, as well as its plugin [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) for managing distinct virtual environments.

#### direnv

[direnv](https://direnv.net/) is another useful, generic development tool, for managing environmental variables.

### Set-up

1. Create a pyenv virtualenv `appy` under Python v3.7.2:

        pyenv virtualenv 3.7.2 appy

1. Install console requirements:

        pip install -r requirement/console.txt

1. Optionally export environment variables such as:

    * `DATABASE_URL=postgres://appy_reviews:PASSWORD@DBHOST:DBPORT/appy_reviews`
    * `AWS_PROFILE`
    * `AWS_EB_PROFILE`

### CLI

Project development, deployment, _etc._ are managed via `argcmdr`:

    manage --help

## Further reading

Refer to the [documentation](doc/).
