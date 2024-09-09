from django.http import HttpResponseRedirect
from urllib.parse import urlencode, parse_qs, urlsplit, urlunsplit

class SmoothNavigationMiddleware:
    """Keep `?back=` query parameter on POST requests."""

    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return self.process_response(request, response)

    def process_response(self, request, response):
        if isinstance(response, HttpResponseRedirect):
            back = request.GET.get('back')
            if back:
                # Split the URL of the 'back' parameter
                _, _, back_path, _, _ = urlsplit(back)

                # Split the URL of the response 'location' header
                scheme, netloc, path, query_string, fragment = urlsplit(response['Location'])
                query_params = parse_qs(query_string)

                # Remove the 'back' parameter if the path matches
                if path == back_path:
                    query_params.pop('back', None)
                elif 'back' not in query_params:
                    query_params['back'] = [back]

                # Reconstruct the new query string
                new_query_string = urlencode(query_params, doseq=True)
                response['Location'] = urlunsplit((scheme, netloc, path, new_query_string, fragment))

        return response
