# SDJ - Segurança Django [![SDJ Dev](https://img.shields.io/badge/SDJ-dev-green.svg)](https://github.com/Cloves23/sdj)
A aplicação SDJ tem como objetivo incrementar as permissões padrão do Django de maneira simplificada e com recursos
adicionais.

> A aplicação **NÃO está finalizada** e ainda está sendo desenvolvida em meu tempo livre.

## Objetivo de Configuração e Uso

### Configuração Inicial
Para configurar, basta instalar a aplicação no projeto e, se desejar, mudar o nome do arquivo de permissões a ser
utilizado. Exemplo:

```python
# NOME_PROJETO/settings.py

INSTALLED_APPS = [
    # ...
    'sdj.apps.SDJConfig',
]

# Configuração opicional
SDJ_PERMISSIONS_MODULE = '.nome_do_modulo'
```

A configuração `SDJ_PERMISSIONS_MODULE` será utilizada para importar funções personalizadas e possíveis classes que
definirão um ou mais grupos de segurança. Se seu valor não for definido, assume-se `.permissions` como padrão.

Com o nome do módulo definido, vale destacar que, dependendo do caso, a aplicação precisará ter um
[módulo](https://www.pythonprogressivo.net/2018/07/Modulo-em-Python-O-Que-e-Para-Que-serve-Como-funciona-Como-usar.html)
nomeado como **permissions** ou com o nome personalizado.

Uma vez configurado, quando executar `python manage.py migrate`, a aplicação atualizará todas as permissões dos grupos,
adicionará ou removerá os usuários dos grupos de acordo com as configurações de cada um.

### Utilização

Considere que existe um modelo chamado **Mensagem** e em uma view, serão
disponibilizados recursos distintos para o usuário com as seguintes restrições:

```python
# ROOT_APP/models.py
from django.db import models

class Mensagem(models.Model):
    criador = models.ForeignKey('auth.User', models.CASCADE)
    destinatario = models.ForeignKey('auth.User', models.CASCADE)
    nome = models.CharField(max_length=50)
    texto = models.TextField()
    visualizada = models.BooleanField()
    # ...
```

1. Usuário pode `add` novas mensagens caso tenha a permissão correspondente;
2. Usuário pode `view` visualizar o que criou ou se for o destinatário;
3. Usuário pode `change` apenas os mensagens não visualizadas;
4. Usuário pode `delete` apenas se for superusuário.

Considerando que o nome do módulo de permissões não foi modificado, temos:

```python
# ROOT_APP/permissions.py
from django.db.models import Q

class GroupUsuario:
    name = 'Usuário'
    users_rules = Q(is_active=True)
    non_users_rules = []
    permissions = {
        'mensagem': ['view']
    }

class GroupMensageiro:
    name = "Mensageiro"
    permissions = {
        'mensagem': ['add', 'view', 'change']
    }

def fnc_acesso_mensagem(usuario, mensagem):
    return mensagem.criador == usuario or mensagem.destinatario == usuario

def fnc_msg_n_visualizada(usuario, mensagem):
    return mensagem.visualizada
```

Como pode-se perceber, para definir cada grupo é necessário que o nome da classe **sempre** inicie com **Group**. Além disso,
também é possível notar que apenas dois atributos apareceram na definição dos dois grupos, `name` e `permissions`,
subentendendo que são obrigatórios. A listagem a seguir mostra mais detalhes sobre cada atributo:

|Atributo       |Opcional|Descrição
|---------------|--------|---------
|name           |Não     |Nome do grupo que será registrado em [`auth.Group`](https://docs.djangoproject.com/en/dev/ref/contrib/auth/#group-model).
|users_rules    |Sim     |Expressão `Q` que define a adição de usuários em um grupo.
|non_users_rules|Sim     |Expressão `Q` que define a remoção de usuários de um grupo.
|permissions    |Não     |Definição das permissões de um modelo da aplicação.

Caso `users_rules` seja definido e `non_users_rules` não, a remoção dos usuários será definida pela negação de
`users_rules` e vice-versa. Se nenhum dos dois forem definidos, a adição ou remoção serão manuais.

O atributo `permissions` deverá ser um dicionário com o nome do modelo como chave, presente em
[`contenttypes.ContentType`](https://docs.djangoproject.com/en/dev/ref/contrib/contenttypes/#the-contenttype-model), e
uma lista como valor contendo os prefixos dos códigos das permissões do django 
([`auth.Permission`](https://docs.djangoproject.com/en/dev/ref/contrib/auth/#permission-model)).

> Prefixos exemplo: `add`, `view`, `change` e `delete`.

Com essas etapas finalizadas, agora é só utilizar nas views como decoradores.

```python
# views.py
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.decorators import login_required

from sdj.decorators import can_, perm_func, perm_obj

from .models import Mensagem


@method_decorator(login_required, name='dispatch')
@method_decorator(can_('add', Mensagem, msg='Mensagem opcional de erro'), name='dispatch')
class CriarMensagem(CreateView):
    model = Mensagem
    # ...

@method_decorator(login_required, name='dispatch')
@method_decorator(can_('view', Mensagem), name='dispatch')
@method_decorator(perm_obj('fnc_acesso_mensagem', Mensagem, msg='Mensagem opcional de Erro'), name='dispatch')
class VisualizarMensagem(DetailView):
    model = Mensagem
    # ...

@method_decorator(login_required, name='dispatch')
@method_decorator(can_('change', Mensagem), name='dispatch')
@method_decorator(perm_obj('fnc_msg_n_visualizada', Mensagem), name='dispatch')
class EditarMensagem(UpdateView):
    model = Mensagem
    # ...

@method_decorator(login_required, name='dispatch')
@method_decorator(perm_func(lambda usuario: usuario.is_superuser,  msg='Mensagem opcional de Erro'), name='dispatch')
class ApagarMensagem(DeleteView):
    model = Mensagem
    # ...
```