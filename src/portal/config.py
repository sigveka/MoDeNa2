"""
Portal configuration - must be imported before any modena import.

Sets MODENA_URI from the environment (defaulting to localhost) so that
modena.SurrogateModel connects to the right MongoDB instance.
"""
import os

# Set default before modena is imported anywhere else in the process.
os.environ.setdefault('MODENA_URI', 'mongodb://localhost:27017/test')
