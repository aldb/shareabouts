import requests
import yaml
import json
import time
import hashlib
import httpagentparser

from django.shortcuts import render
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from proxy.views import proxy_view


def make_resource_uri(dataset, resource, root=settings.SHAREABOUTS_API_ROOT):
    resource = resource.strip('/')
    dataset = dataset.strip('/')
    root = root.rstrip('/')
    uri = '%s/datasets/%s/%s/' % (root, dataset, resource)
    return uri


class ShareaboutsApi (object):
    def __init__(self, dataset, root=settings.SHAREABOUTS_API_ROOT):
        self.root = root
        self.dataset = dataset

    def get(self, resource, default=None, **kwargs):
        uri = make_resource_uri(self.dataset, resource, root=self.root)
        res = requests.get(uri, params=kwargs,
                           headers={'Accept': 'application/json'})
        return (res.text if res.status_code == 200 else default)


@ensure_csrf_cookie
def index(request):
    # Load app config settings
    with open(settings.SHAREABOUTS_CONFIG) as config_yml:
        config = yaml.load(config_yml)

    # TODO: Is it weird to get the API_ROOT and the dataset path from
    # separate config files?

    # Get initial data for bootstrapping into the page.
    api = ShareaboutsApi(dataset=config['dataset'])

    place_types_json = json.dumps(config['place_types'])
    place_type_icons_json = json.dumps(config['place_type_icons'])
    survey_config_json = json.dumps(config['survey'])
    support_config_json = json.dumps(config['support'])
    map_config_json = json.dumps(config['map'])
    place_config_json = json.dumps(config['place'])

    # TODO These requests should be done asynchronously (in parallel).
    places_json = api.get('places', default=u'[]')
    activity_json = api.get('activity', limit=20, default=u'[]')

    # Get the content of the static pages linked in the menu.
    pages_config = config.get('pages', [])
    for page_config in pages_config:
        external = page_config.get('external', False)

        page_url = page_config.pop('url')
        page_url = request.build_absolute_uri(page_url)
        page_config['url'] = page_url

        if external:
            page_config['external'] = True

        else:
            # TODO It would be best if this were also asynchronous.
            response = requests.get(page_url)

            # If we successfully got the content, stick it into the config instead
            # of the URL.
            if response.status_code == 200:
                page_config['content'] = response.text

            # If there was an error, let the client know what the URL, status code,
            # and text of the error was.
            else:
                page_config['status'] = response.status_code
                page_config['error'] = response.text

    pages_config_json = json.dumps(pages_config)

    # The user token will be a pair, with the first element being the type
    # of identification, and the second being an identifier. It could be
    # 'username:mjumbewu' or 'ip:123.231.132.213', etc.  If the user is
    # unauthenticated, the token will be session-based.
    if 'user_token' not in request.session:
        t = int(time.time() * 1000)
        ip = request.META['REMOTE_ADDR']
        unique_string = str(t) + str(ip)
        session_token = 'session:' + hashlib.md5(unique_string).hexdigest()
        request.session['user_token'] = session_token
        request.session.set_expiry(0)

    user_token_json = u'"{0}"'.format(request.session['user_token'])

    # Get the browser that the user is using.
    user_agent_string = request.META['HTTP_USER_AGENT']
    user_agent = httpagentparser.detect(user_agent_string)
    user_agent_json = json.dumps(user_agent)

    context = {'places_json': places_json,
               'activity_json': activity_json,
               'place_types_json': place_types_json,
               'place_type_icons_json': place_type_icons_json,
               'survey_config_json': survey_config_json,
               'support_config_json': support_config_json,
               'user_token_json': user_token_json,
               'pages_config_json': pages_config_json,
               'map_config_json': map_config_json,
               'place_config_json': place_config_json,
               'user_agent_json': user_agent_json}
    return render(request, 'index.html', context)


def api(request, path):
    """
    A small proxy for a Shareabouts API server, exposing only
    one configured dataset.
    """
    with open(settings.SHAREABOUTS_CONFIG) as config_yml:
        config = yaml.load(config_yml)
    dataset = config['dataset']
    api_key = config['dataset_api_key']
    url = make_resource_uri(dataset, path)
    headers = {'X-Shareabouts-Key': api_key}
    return proxy_view(request, url, requests_args={'headers': headers})
