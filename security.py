from copy import deepcopy
from importlib import import_module

from django.apps import apps
from django.conf import settings
from django.core.exceptions import AppRegistryNotReady
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
try:
    from django.contrib.auth.models import Group as DjGroup
except AppRegistryNotReady:
    DjGroup = apps.get_model('auth', 'Group')
try:
    from django.contrib.auth.models import Permission
except AppRegistryNotReady:
    Permission = apps.get_model('auth', 'Permission')
try:
    from django.contrib.auth.models import User
except AppRegistryNotReady:
    User = apps.get_model('auth', 'User')

_groups_manager = None
_groups_cache = {}
_module_permissions_cache = {}


class Management:
    @staticmethod
    def init_groups(sender, *args, **kwargs):
        global _groups_cache
        _groups_cache.clear()
        Management.process_groups(sender.apps.app_configs)

    @staticmethod
    def process_groups(app_configs=apps.app_configs):
        groups = GroupsManager()
        for app_name in app_configs:
            try:
                groups_perms = Management.app_permissions(app_name)
            except (SystemError, ModuleNotFoundError):
                continue
            for gp_name in filter(lambda m: m.startswith('Group'), dir(groups_perms)):
                group_app = getattr(groups_perms, gp_name)
                group = groups.get(group_app.name)
                if not group:
                    group = MetaGroup(group_app.name, getattr(group_app, 'users_rules', None),
                                      getattr(group_app, 'non_users_rules', None))
                else:
                    if hasattr(group_app, 'users_rules'):
                        if isinstance(group_app.users_rules, list):
                            group._add_users_rules(group_app.users_rules)
                        else:
                            group._add_users_rules(group_app.users_rules)
                    if hasattr(group_app, 'non_users_rules'):
                        if isinstance(group_app.non_users_rules, list):
                            group._add_non_users_rules(group_app.non_users_rules)
                        else:
                            group._add_non_users_rules(group_app.non_users_rules)
                if hasattr(group_app, 'permissions'):
                    group._add_perms({app_name: group_app.permissions})
            groups.update_groups()

    @staticmethod
    def app_permissions(root_app):
        """
        Gets the permissions module for an app. The module name will assume "APP_PERMISSIONS_MODULE", if set to
        "settings", or ".permissions".

        :param root_app: Name of the app.
        :return: The respective module.
        """
        global _module_permissions_cache
        module = getattr(settings, 'APP_PERMISSIONS_MODULE', '.permissions')
        if root_app in _module_permissions_cache:
            return _module_permissions_cache[root_app]
        module = import_module(module, root_app)
        _module_permissions_cache[root_app] = module
        return module

    @staticmethod
    def get_object_permission_func(root_app, name):
        """
        Gets the function by name in an app permissions module.

        :param root_app: Name of the app.
        :param name: Name of the desired function.
        :return: A function or an attribute defined in the module.
        """
        return getattr(Management.app_permissions(root_app), name)


class MetaGroup:
    _permissions = None
    _users_rules = None
    _non_users_rules = None

    def __new__(cls, name: str, users_rules: list=None, non_users_rules: list=None):
        global _groups_cache
        name = name.strip(' ')
        if not name:
            raise ValueError(_('The group received no name.'))
        elif name in _groups_cache:
            return _groups_cache[name]
        if isinstance(users_rules, list):
            users_rules = users_rules[:]
        elif users_rules is not None:
            users_rules = [users_rules]
        if isinstance(non_users_rules, list):
            non_users_rules = non_users_rules[:]
        elif non_users_rules is not None:
            non_users_rules = [non_users_rules]

        def new(klass):
            return super().__new__(klass)
        group = type('GroupSDJ', (cls,), {  # TODO: Verificar uma maneira de melhorar esse trecho
            '_users_rules': users_rules, '_non_users_rules': non_users_rules, '_permissions': {}, '__new__': new
        })
        group = group()
        group.djgroup = DjGroup.objects.get_or_create(name=name)[0]
        _groups_cache[name] = group
        return group

    def __str__(self):
        return str(self.djgroup)

    def __repr__(self):
        return f'<GroupSDJ: {self.djgroup.name}>'

    @property
    def name(self):
        return self.djgroup.name

    def _add_perms(self, new_perms):
        """
        Update the permissions set.

        :param new_perms: {'app_name': {'model_name': ['add', 'change', ...], ...}, ...}
        """
        for app in new_perms:
            if app not in self._permissions:
                self._permissions[app] = deepcopy(new_perms[app])
            else:
                for modelo in new_perms[app]:
                    if modelo not in self._permissions[app]:
                        self._permissions[app][modelo] = deepcopy(new_perms[app][modelo])
                    else:
                        self._permissions[app][modelo].extend(new_perms[app][modelo])

    def _add_users_rules(self, rules):
        if not isinstance(rules, list):
            rules = [rules]
        if self._users_rules:
            self._users_rules.extend(rules)
        else:
            self._users_rules = rules

    def _add_non_users_rules(self, rules):
        if not isinstance(rules, list):
            rules = [rules]
        if self._non_users_rules:
            self._non_users_rules.extend(rules)
        else:
            self._non_users_rules = rules

    @property
    def filter_perms(self):
        """
        Convert the permitions dictionary to a "Q" expression.

        :return: Filter of "Q" expression.
        """
        filtro = None
        for app, modelos_perms in self._permissions.items():
            for modelo in modelos_perms:
                filtro_perm = Q(codename__startswith=modelos_perms[modelo][0])
                for perm in modelos_perms[modelo][1:]:
                    filtro_perm = filtro_perm | Q(codename__startswith=perm)
                if filtro:
                    filtro = filtro | Q(filtro_perm, content_type__app_label=app, content_type__model=modelo)
                else:
                    filtro = Q(filtro_perm, content_type__app_label=app, content_type__model=modelo)
        return filtro

    def users(self, *args, **kwargs):
        """
        Search the list of users of the group.

        :return: QuerySet of "User".
        """
        return self.djgroup.user_set.filter(*args, **kwargs)

    def add_users(self, user_s):
        """
        Adds one or more users to the group.

        :param user_s: User or list of users.
        :attention: When occurs a migration, the function "update_group" is executed and can change the list of users
                    in the group.
        """
        if isinstance(user_s, User):
            self.djgroup.user_set.add(user_s)
        else:
            self.djgroup.user_set.add(*user_s)

    def remove_users(self, user_s):
        """
        Remove one o more users in the group.

        :param user_s: User or list of users.
        :attention: When occurs a migration, the function "update_group" is executed and can change the list of users
                    in the group.
        """
        if isinstance(user_s, User):
            self.djgroup.user_set.remove(user_s)
        else:
            self.djgroup.user_set.remove(*user_s)

    def check_for_new_users(self):
        """
        Search for new users who are not in the group.

        :return: QuerySet of "User"
        :raise ValueError: Case rules for new users is not defined.
        """
        if self._users_rules is not None:
            return User.objects.filter(*self._users_rules, ~Q(groups=self.djgroup))
        return User.objects.none()

    def check_for_non_users(self):
        """
        Search for users who should not be in the group.

        :return: QuerySet of "User"
        :raise ValueError: Case rules for non users is not defined.
        """
        if self._non_users_rules is not None:
            return User.objects.filter(*self._non_users_rules, Q(groups=self.djgroup))
        return User.objects.none()

    def update_group(self):
        """
        Update the permissions and list of users in the group.
        """
        self.update_permissions()
        self.update_users()

    def update_permissions(self):
        """
        Update group permissions.
        """
        filtro = self.filter_perms()
        if filtro:
            perms = Permission.objects.filter(filtro)
            self.djgroup.permissions.add(*perms)
            self.djgroup.permissions.remove(*self.djgroup.permissions.difference(perms))

    def update_users(self):
        """
        Updates the list of users in the group.
        """
        self.add_users(self.check_for_new_users())
        self.remove_users(self.check_for_non_users())

    def check_user(self, user: User):
        """
        Evaluates whether a User is able to belong to the group to add or remove it.

        :param user: User
        """
        if self.check_for_non_users().filter(pk=user.pk).exists():
            self.remove_users(user)
            return False
        elif self.check_for_new_users().filter(pk=user.pk).exists():
            self.add_users(user)
            return True


class GroupsManager:
    def __new__(cls, *args, **kwargs):
        global _groups_manager
        if not _groups_manager:
            _groups_manager = super(GroupsManager, cls).__new__(cls, *args, **kwargs)
        return _groups_manager

    def __repr__(self):
        global _groups_cache
        qtd = len(_groups_cache)
        return f'<SDJ/GroupsManager: {qtd} group{"s" if qtd != 1 else ""}>'

    def __getitem__(self, group_name):
        global _groups_cache
        return _groups_cache[group_name]
    get = __getitem__
    group = __getitem__

    # def get(self, group_name):
    #     global _groups_cache
    #     return _groups_cache.get(group_name, None)

    @property
    def groups(self):
        global _groups_cache
        return tuple(_groups_cache.values())

    def update_group(self, group_name):
        self[group_name].update_group()

    def update_groups(self):
        global _groups_cache
        for group in _groups_cache:
            _groups_cache[group].update_group()

    def users_group(self, group_name, *args, **kwargs):
        return self[group_name].users(*args, **kwargs)

    def check_user_groups(self, user):
        global _groups_cache
        res = False
        for group in _groups_cache:
            res = res or _groups_cache[group].check_user(user)
        return res
