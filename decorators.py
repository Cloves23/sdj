from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from .security import Management


def perm(permission: str, login_url: str=None, staff: bool=True, exception: bool=True, msg: str=None):
    """
    Check if user has a given permission.

    :param permission: Complete permission name. Ex.: app.add_model;
    :param login_url: If necessary, login URL to reddirect. Default: None;
    :param staff: Indicate if staff user have total access. Default: True;
    :param exception: Throw PermissionDenied instead redirecto to the login_url. Default: True;
    :param msg: Exception custom message. Default: None.
    :return: Resultant decorator.
    """
    def check_perms(user):
        if staff and user.is_staff or user.has_perm(permission):
            return True
        if exception:
            raise PermissionDenied(msg or _('Unauthorized access.'))
        return False

    return user_passes_test(check_perms, login_url=login_url)


def can_(opts, model, login_url: str=None, staff: bool=True, exception: bool=True, msg: str=None):
    """
    Checks whether the user has one or more permissions for a model based on the permissions prefixes, such as "add"
    and "change".

    :param opts: String ou lista com os prefixos dos nomes das permissões;
    :param model: Subclass of models.Model to verify the permissions;
    :param login_url: If necessary, login URL to reddirect. Default: None;
    :param staff: Indicate if staff user have total access. Default: True;
    :param exception: Throw PermissionDenied instead redirecto to the login_url. Default: True;
    :param msg: Exception custom message. Default: None.
    :return: Decorator resultante
    """
    def check_perms(user):
        perms = [
            f'{model._meta.app_label}.{opt}_{model._meta.model_name}'
            for opt in ([opts] if isinstance(opts, str) else opts)
        ]
        if staff and user.is_staff or user.has_perms(perms):
            return True
        if exception:
            raise PermissionDenied(msg or _('Unauthorized access.'))
        return False

    return user_passes_test(check_perms, login_url=login_url)


def perm_func(func, login_url: str = None, excecao: bool = True, msg: str = None):
    """
    Verifica a permissão a partir de uma função personalizada inserindo como primeiro parâmetro o usuário logado.

    :param func: função a ser executada;
    :param login_url: string com a URL de login, caso a execução da função tenha retornado False;
    :param excecao: Boleano que permite o lançamento da exceção PermissionDenied;
    :param msg: String com a mensagem personalizada para a exceção.
    :return: Decorator resultante
    """

    def check_perms(user):
        if user.is_active and user.is_superuser or func(user):
            return True
        if excecao:
            raise PermissionDenied(msg or _('Unauthorized access.'))
        return False

    return user_passes_test(check_perms, login_url=login_url)


def perm_obj(name_func: str, model, pk=None, pk_pos: int = 0, busca: dict = None, msg: str = None):
    """
    Verifica se um usuário possui permissão sob um objeto por meio do nome de uma função inserindo como primeiro
    parâmetro o usuário logado, depois a instância.

    :param name_func: String com nome da função contida no arquivo ".permissoes" da aplicação pertencente ao objeto;
    :param model: Subclasse de models.Model;
    :param pk: Valor da chave primária alvo;
    :param pk_pos: Posição da chave primária nos parâmetros da view desconsiderando o primeiro parâmetro;
    :param busca: Dicionario contendo filtros personalizados;
    :param msg: String com a mensagem personalizada para a exceção.
    :return: Decorator resultante
    """

    def check_perm(func):
        @wraps(func)
        def check(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.is_active:
                if not request.user.is_superuser:
                    pesq = {"pk": None}
                    if busca:
                        pesq = busca
                    elif pk or "pk" in kwargs:
                        pesq["pk"] = pk or kwargs.get("pk")
                    elif len(args) >= pk_pos + 1:
                        pesq["pk"] = args[pk_pos]
                    instancia = model.objects.filter(**pesq)
                    if instancia.count() <= 1:
                        instancia = instancia.first()
                    metodo = Management.get_object_permission_func(
                        request.resolver_match._func_path[:request.resolver_match._func_path.find(".")], name_func
                    )
                    if not metodo(request.user, instancia):
                        raise PermissionDenied(msg or _('Unauthorized access.'))
                return func(request, *args, **kwargs)
            raise PermissionDenied(_('You must be logged in to access this data.'))

        return check

    return check_perm


def perm_objs(name_func: str, models, campos=None, msg: str = None):
    """
    Verifica se um usuário possui permissão sob um ou mais objetos por meio do nome de uma função inserindo como
    primeiro parâmetro o usuário logado, depois a(s) instância(s).

    :param name_func: String com nome da função contida no arquivo ".permissoes" da aplicação pertencente ao objeto;
    :param models: Lista de subclasses de models.Model;
    :param campos: Lista com sequência correspondente aos modelos com os campos que serão utilizados para filtra-los. Padrão "pk";
    :param msg: String com a mensagem personalizada para a exceção.
    :return: Decorator resultante
    """
    if not isinstance(models, (list, tuple)):
        models = [models]

    def check_perm(func):
        @wraps(func)
        def check(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.is_active:
                if not request.user.is_superuser:
                    metodo = Management.get_object_permission_func(
                        request.resolver_match._func_path[:request.resolver_match._func_path.find(".")], name_func
                    )
                    instancias = [
                        models[i].objects.filter(**{campos[i] if campos else "pk": args[i]}).first()
                        for i in range(len(models))
                    ]
                    if not metodo(request.user, *instancias):
                        raise PermissionDenied(msg or _('Unauthorized access.'))
                return func(request, *args, **kwargs)
            raise PermissionDenied(_('You must be logged in to access this data.'))

        return check

    return check_perm
