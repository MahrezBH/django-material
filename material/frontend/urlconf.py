from __future__ import unicode_literals

try:
    from urllib.parse import quote
except:
    from urllib import quote

from django.urls import  URLResolver, Resolver404
from django.http.request import QueryDict
import six


class ModuleMatchName(str):
    """Dump str wrapper.

    Just to keep module reference over django url resolve calling
    hierarhy.
    """


class ModuleURLResolver(URLResolver):
    """Module URL Resolver.

    A wrapper around URLResolver that check the module installed
    state. And allows access to the resolved current module at runtime.

    Django reads url config once at the start. Installation and
    deisntallation the module at runtime don't produce change in the
    django url-conf.

    Url access check happens at the resolve time.
    """

    def __init__(self, *args, **kwargs):  # noqa D102
        self._module = kwargs.pop('module')
        super(ModuleURLResolver, self).__init__(*args, **kwargs)

    def resolve(self, *args, **kwargs):  # noqa D102
        result = super(ModuleURLResolver, self).resolve(*args, **kwargs)

        if result and not getattr(self._module, 'installed', True):
            raise Resolver404({'message': 'Module not installed'})

        result.url_name = ModuleMatchName(result.url_name)
        result.url_name.module = self._module

        return result


def frontend_url(request, url=None, back_link=None, absolute=True):
    """Construct an url for a frontend view.

    :keyword back: type of the back link to be added to the query string
                   - here: link to the current request page
                   - here_if_none: add link only if there is no `back` parameter
    :keyword absolute: construct absolute url, including host name

    namespace = self.ns_map[task.process.flow_class]
    return frontend_url(
        self.request,
        flow_url(namespace, task, 'index', user=request.user),
        back='here')
    """
    params = QueryDict(mutable=True)
    for key, value in six.iterlists(request.GET):
        if not key.startswith('datatable-') and key != '_':
            params.setlist(key, value)

    if back_link == 'here_if_none' and 'back' in params:
        # Do nothing
        pass
    elif back_link is not None:
        if params:
            back = "{}?{}".format(quote(request.path), quote(params.urlencode()))
        else:
            back = "{}".format(quote(request.path))
        params['back'] = back

    if url is not None:
        location = '{}?{}'.format(url, params.urlencode())
        return request.build_absolute_uri(location) if absolute else location
    else:
        return params.urlencode()
