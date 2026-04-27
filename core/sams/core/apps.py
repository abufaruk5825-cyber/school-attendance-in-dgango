from django.apps import AppConfig


class CoreConfig(AppConfig):
    # Fully-qualified name prevents collision with the real 'core' app
    name = 'core.sams.core'
