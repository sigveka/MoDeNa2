"""
Defaults shared by every MoDeNa entry point.

Import-safe: no side effects, no dependencies.  ``modena.SurrogateModel``
connects to MongoDB when imported, so a constant that the CLI, the portal and
the library must agree on cannot live there.

It lives here because it was duplicated and the copies drifted:
``SurrogateModel`` connected to ``.../test`` while ``modena doctor`` reported
``.../modena`` -- so with MODENA_URI unset, doctor printed one database and
checked another.
"""

#: The MongoDB URI used when MODENA_URI is not set.  Changing it moves every
#: user who relies on the default to an empty database, so do not.
DEFAULT_MODENA_URI = 'mongodb://localhost:27017/test'
