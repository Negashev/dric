import os
import logging
import json
import requests
import www_authenticate
from requests.auth import HTTPBasicAuth
from japronto import Application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

class RegistryApi( object ):
    def __init__( self, user, token ):
        self.user  = user
        self.token = token

    @staticmethod
    def get_bearer_token( user, token, service, scope, realm ):
        # https://stackoverflow.com/a/23497912/2860751
        payload_str = "&".join("%s=%s" % (k,v) for k,v in { "scope": scope, "service": service}.items())
        r = requests.get( realm, auth=HTTPBasicAuth( user, token ), params=payload_str )
        return json.loads( r.content )['token']

    @staticmethod
    def get_auth_header( url, method ):
        r = getattr( requests, method )( url )
        if r.status_code == 401:
            try:
                r.headers['Www-Authenticate']
            except KeyError:
                raise Exception('could not fetch bearer info from registry endpoint')
            else:
                return www_authenticate.parse( r.headers['Www-Authenticate'] )
        else:
            raise 'invalid auth_header response code' + str( r.status_code )

    @staticmethod
    def get_result( url, method, token ):
        if method == "head":
            r = requests.head( url, headers={ 'Accept': 'application/vnd.docker.distribution.manifest.v2+json', 'Authorization': 'Bearer ' + token } )
            return( r.headers )
        else:
            r = getattr( requests, method )( url, headers={ 'Authorization': 'Bearer ' + token } )
            if method == "delete":
                return r.content
            else:
                return( json.loads( r.content ) )

    def query( self, url, method='get' ):
        params = self.get_auth_header( url, method )
        try:
            params['Bearer']
        except KeyError:
            raise Exception('could not fetch bearer info from registry endpoint')
        else:
            return self.get_result( url, method, self.get_bearer_token( self.user, self.token, params['Bearer']['service'], params['Bearer']['scope'], params['Bearer']['realm'] ) )



logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(u'%(levelname)-8s [%(asctime)s]  %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
# basic sec urity, add this token to the project's webhook
# get one:
# < /dev/urandom tr -dc _A-Z-a-z-0-9 | head -c"${1:-32}";echo;
token = os.getenv('CLEAN_TOKEN')
registry_url = os.getenv('REGISTRY_URL')

CATALOG = []
REGISTRY = RegistryApi(
    user=os.getenv('REGISTRY_LOGIN'),
    token=os.getenv('REGISTRY_TOKEN')
)
if 'DRY_RUN' in os.environ:
    dry_run = True
else:
    dry_run = False


async def batch_remove(request):
    if 'clean-token' in request.query and request.query['clean-token'] == token:
        project_namespace = request.match_dict['project_namespace']
        project_name = request.match_dict['project_name']
        tag = request.match_dict['tag']
        logger.info(f"Valid request, processing {', '.join(request.match_dict.values())}")
        await cleanup(request.registry, project_namespace, project_name, tag)
        return request.Response(text='ok')

    return request.Response(text='request not valid')


async def single_remove(request):
    if 'clean-token' in request.query and 'path' in request.query and request.query['clean-token'] == token:
        logger.info(f"Valid request, processing {request.query['path']}")
        image, tag = request.query['path'].split(':')
        await remove(request.registry, image, tag)
        return request.Response(text='ok')

    return request.Response(text='request not valid')


async def cleanup(registry, project_namespace, project_name, tag):
    logger.info("Merge detected")
    global CATALOG
    this_repo_image = "%s/%s" % (project_namespace, project_name)
    # find all images
    this_catalog = CATALOG
    for i in this_catalog:
        if i.startswith(this_repo_image):
            await remove(registry, i, tag)


async def remove(registry, image, tag):
    try:
        print(f"Try remove {registry_url}/{image}:{tag}")
        digest = registry.query(f"{registry_url}/v2/{image}/manifests/{tag}", 'head')['Docker-Content-Digest']
        return registry.query(f"{registry_url}/v2/{image}/manifests/{digest}", 'delete')
    except Exception as e:
        print(f"Error remove {registry_url}/{image}:{tag} :{e}")


async def get_catalog(first_load=False):
    if first_load:
        print(f"First load {registry_url}/v2/_catalog, please wait...")
    global CATALOG
    global REGISTRY
    this_catalog = REGISTRY.query(f"{registry_url}/v2/_catalog", 'get')['repositories']
    if len(this_catalog) != len(CATALOG):
        print(f"Found {len(this_catalog)} repositories")
    CATALOG = this_catalog


async def connect_scheduler():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(get_catalog, 'interval', seconds=int(os.getenv('DRIC_SECONDS_CATALOG', 300)), max_instances=1)
    scheduler.start()


async def index(request):
    global CATALOG
    return request.Response(json=CATALOG)


app = Application()
app.extend_request(lambda x: REGISTRY, name='registry', property=True)
app.loop.run_until_complete(get_catalog(first_load=True))
app.loop.run_until_complete(connect_scheduler())
router = app.router
router.add_route('/{project_namespace}/{project_name}/{tag}', batch_remove)
router.add_route('/extra_path', single_remove)
router.add_route('/', index)
app.run(host='0.0.0.0', port=80, debug=True)
