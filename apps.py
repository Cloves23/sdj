from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SDJConfig(AppConfig):
    name = 'sdj'

    def ready(self):
        from .security import Management
        post_migrate.connect(Management.init_groups, sender=self.apps.app_configs["auth"])
